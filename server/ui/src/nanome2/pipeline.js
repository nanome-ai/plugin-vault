/*
 * Nanome v1 session (.nanome / .nanoscenes) -> a new Nanome 2 workspace. No LLM in the loop.
 *
 *   1. MARA runs the ".Nanome v1 Session Importer" custom tool on the file
 *      (POST {mara}/api/tools/{id}/run) and answers with the tool's summary and output names.
 *      Converted mode skips this: the outputs come from a URL (a local server), already made
 *      by v1-parser-tool's tool/tool_main.py (prepare_local.py).
 *   2. The outputs are downloaded: one structure file per v1 complex (PDB, mmCIF or SDF), the
 *      components JSON, the annotations JSON when the session has measurements, and the image
 *      annotations JSON with its PNG / JPEG files when it has images or PDF pages.
 *   3. The Workspace API gets a new workspace, the structure files in the tool's order
 *      (entries/load-multiple, one file per request), the components with their EntrySerial
 *      filters remapped to the serials the loads returned (those of structures hidden in v1
 *      hidden with v2's component flag), the annotations (GraphQL add*Annotations) and the
 *      image annotations (created, then their pictures uploaded). A session with nothing v2 can
 *      show still gets its workspace, empty as v1 opens it, with the tool's reason as a warning.
 *   4. Every entry's stored models are read back and compared with the converted files: atom
 *      counts, coordinates, elements, formal charges and bond orders.
 *
 * A pure ES module: no extension APIs and no DOM. The extension's service worker imports it,
 * build_page_bundle.py inlines it into page_bundle.js for the DevTools console, and Node 18+
 * can import it (global fetch, FormData and Blob; other implementations can be passed in).
 * It must not import anything: build_page_bundle.py strips the `export` keywords and wraps it.
 */

export const DEFAULTS = Object.freeze({
  maraUrl: 'https://app.nanome.ai',
  toolId: '01M32ZZKF3RPH80EBW73T2VVKZ', // ".Nanome v1 Session Importer" on MARA
  toolArgs: Object.freeze({ exact_colors: false, structure_format: 'auto', frames: 'all' }),
  entryNames: 'complex', // 'complex': v2 entries take the v1 complex names; 'file': the output file names
  verify: true,
  verifyModels: 12, // models read back per entry: first, last and evenly spaced between
  verifyAtoms: 5, // atoms per model reported side by side (every atom is compared)
  verifyDetail: 'summary', // 'full' adds v2's stored per-atom arrays of every compared model
  tolerance: 0.002, // angstrom; v2 keeps coordinates on a 0.001 A grid
  freeEntryLimit: 5, // structures a free license may hold in one workspace
  slowLoadSeconds: 120, // a structure file v2 takes longer than this to load is named in the warnings
  // a load request v2 drops or answers 502/503/504 (a huge file can outlast the gateway while v2
  // goes on loading it): the workspace is read every loadPollSeconds until the entry shows up.
  // One budget per import: at most loadRecoverMax such loads are waited for, loadRecoverSeconds
  // in all; past that a failed load fails the import at once, as it would without
  loadRecoverSeconds: 300,
  loadRecoverMax: 2,
  loadPollSeconds: 10,
  // a workspace creation v2 refuses because it ran into another change to the account's
  // workspaces (HTTP 400, nothing created: isConcurrencyFailure) is sent again, up to
  // workspaceRetries more times, after a pause that grows by workspaceRetrySeconds each time
  workspaceRetries: 5,
  workspaceRetrySeconds: 2,
  deleteToolRun: false, // delete MARA's copy of the upload and outputs once the workspace is built
});

const SESSION_EXTENSION = /\.(nanome|nanoscenes)$/i;
const MAX_BODY = 20000;
const EXAMPLES = 20; // mismatches listed per kind and model

/** A failed step. `step` names it; `status` and `body` are the server's answer when there was one. */
export class ImportFailure extends Error {
  constructor(step, message, { status = null, body = '', url = null } = {}) {
    super(`${step}: ${message}`);
    this.name = 'ImportFailure';
    this.step = step;
    this.status = status;
    this.body = typeof body === 'string' ? body.slice(0, MAX_BODY) : '';
    this.url = url;
    this.partial = {};
  }

  toJSON() {
    const { name, step, message, status, body, url, partial } = this;
    return { name, step, message, status, body, url, partial };
  }
}

// --- small helpers ----------------------------------------------------------------------------

function trimSlash(url) {
  return String(url || '').replace(/\/+$/, '');
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function byteSize(bytes) {
  if (!bytes) return 0;
  if (typeof bytes.byteLength === 'number') return bytes.byteLength; // ArrayBuffer, typed array
  if (typeof bytes.size === 'number') return bytes.size; // Blob, File
  return 0;
}

/** MARA's UI keeps {token, disclaimerAccepted} as JSON under localStorage 'nanome-token'
 * (pinia-plugin-persist). Returns the token or null. */
export function tokenFromStorage(raw) {
  if (typeof raw !== 'string' || !raw) return null;
  try {
    const value = JSON.parse(raw);
    if (value && typeof value.token === 'string' && value.token) return value.token;
    return typeof value === 'string' && value ? value : null;
  } catch {
    return /^[\w.~+/=-]+$/.test(raw) ? raw : null;
  }
}

export function sessionStem(filename) {
  const base = String(filename || '').split(/[\\/]/).pop();
  return base.replace(SESSION_EXTENSION, '').trim() || 'session';
}

export function workspaceNameFor(filename) {
  return `${sessionStem(filename)} (from v1)`;
}

/** The name the session is uploaded to MARA under. MARA writes the upload to
 * os.path.join(files_dir, file.filename), so keep it plain. */
export function uploadNameFor(filename) {
  const base = String(filename || '').split(/[\\/]/).pop();
  const match = SESSION_EXTENSION.exec(base);
  const extension = match ? match[0].toLowerCase() : '.nanome';
  const stem = (match ? base.slice(0, match.index) : base)
    .replace(/[^A-Za-z0-9_.-]/g, '_')
    .replace(/^[._]+/, '');
  return (stem || 'session') + extension;
}

/** The name a structure file is loaded into v2 under. v2 names the entry after the file name up
 * to its last dot, so the v1 complex name
 * makes the entry list read like v1's. Falls back to the tool's own file name. */
export function entryUploadName(displayName, format, fallback) {
  const clean = String(displayName || '')
    .replace(/[\\/:*?"<>|\u0000-\u001f\u007f]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^\.+/, '')
    .slice(0, 80)
    .trim();
  return clean ? `${clean}.${format}` : fallback;
}

// --- the tool's outputs -------------------------------------------------------------------------

/** "Structure files, in load order:" lines of the tool summary (v1-parser-tool's
 * tool/tool_main.py, convert()), or null when the summary has no such list or a line in it cannot
 * be read. */
function summaryStructureLines(summary) {
  const lines = String(summary || '').split(/\r?\n/);
  const start = lines.findIndex(line => line.trim() === 'Structure files, in load order:');
  if (start < 0) return null;
  const listed = [];
  for (let i = start + 1; i < lines.length && lines[i].trim(); i++) {
    const m = /^\s+(\d+)\. ([A-Za-z0-9_.]+\.(?:pdb|cif|sdf)) - (.*), (\d+) atoms(?:,|$)/.exec(lines[i]);
    if (m) listed.push({ index: Number(m[1]), file: m[2], name: m[3], atoms: Number(m[4]), openFrame: openingFrame(lines[i]) });
    else if (/^\s+\d+\. /.test(lines[i])) return null;
  }
  return listed;
}

/** The frame v1 opens a structure on (1-based) when the file holds every frame: the summary
 * line reads "..., 5 frames; v1 opens it on frame 3" (tool_main.py convert()). Null otherwise,
 * including "only frame 3 of 90 written", where the file holds that one frame. */
function openingFrame(line) {
  const m = /, (\d+) frames; v1 opens it on frame (\d+)/.exec(line);
  if (!m) return null;
  const frame = Number(m[2]);
  return frame >= 1 && frame <= Number(m[1]) ? frame : null;
}

/** The complex name the tool gave a file `<base>_NN_<name>.<ext>`, or the file's stem. */
function nameFromFile(file, base) {
  const m = base ? new RegExp(`^${escapeRegExp(base)}_\\d+_(.+)\\.(?:pdb|cif|sdf)$`, 'i').exec(file) : null;
  return m ? m[1] : file.replace(/\.[^.]*$/, '');
}

/**
 * Which of MARA's `filenames` are what, in load order.
 *
 * The tool writes `<base>_components.json`, `<base>_NN_<complex>.<pdb|cif|sdf>` with NN the entry
 * serial its components use (1..N), and `<base>_annotations.json` / `_measurements.json` when the
 * session has measurements (tool_main.py convert()). MARA lists the files in no particular order
 * (a set difference), so the order comes from NN, and the summary's
 * own list must agree with it.
 */
export function parseToolOutputs(summary, filenames) {
  if (typeof summary !== 'string' || !summary.trim()) throw new Error('the tool returned no summary text');
  const files = Array.isArray(filenames) ? filenames.filter(f => typeof f === 'string') : [];
  const componentFiles = files.filter(f => f.endsWith('_components.json'));
  if (componentFiles.length !== 1) {
    throw new Error(`expected one *_components.json among the returned files, got ${componentFiles.length}: ${files.join(', ') || 'none'}`);
  }
  const componentsFile = componentFiles[0];
  const base = componentsFile.slice(0, -'_components.json'.length);
  const pattern = new RegExp(`^${escapeRegExp(base)}_(\\d+)_[A-Za-z0-9_.]*\\.(pdb|cif|sdf)$`);
  const numbered = [];
  for (const file of files) {
    const m = pattern.exec(file);
    if (m) numbered.push({ index: Number(m[1]), file, format: m[2] });
  }
  numbered.sort((a, b) => a.index - b.index);
  numbered.forEach((s, i) => {
    if (s.index !== i + 1) throw new Error(`structure files are not numbered 1..${numbered.length}: ${numbered.map(x => x.file).join(', ')}`);
  });

  const warnings = [];
  const listed = summaryStructureLines(summary);
  if (listed === null) {
    if (numbered.length) warnings.push('The tool summary has no readable "Structure files, in load order" list; the load order comes from the file names.');
  } else if (listed.length !== numbered.length || listed.some((l, i) => l.file !== numbered[i].file || l.index !== numbered[i].index)) {
    throw new Error(`the summary lists [${listed.map(l => l.file).join(', ')}] but MARA returned [${numbered.map(s => s.file).join(', ')}]`);
  }
  const declared = /: (\d+) structure\(s\)\./.exec(summary);
  if (declared && Number(declared[1]) !== numbered.length) {
    throw new Error(`the summary says ${declared[1]} structure(s) but ${numbered.length} structure file(s) came back`);
  }

  const optional = suffix => (files.includes(base + suffix) ? base + suffix : null);
  const annotationsFile = optional('_annotations.json');
  const measurementsFile = optional('_measurements.json');
  // v1's metadata in full (Frames > Meta Data); v2 has no place for most of it, so it is
  // returned to the user with the tool run rather than loaded.
  const metadataFile = optional('_metadata.json');
  // v1's images and PDF pages as v2 image annotations (the files they name are the _media_ ones)
  const imageAnnotationsFile = optional('_image_annotations.json');
  if (!annotationsFile && summary.includes(`${base}_annotations.json`)) {
    throw new Error(`the summary names ${base}_annotations.json but MARA did not return it`);
  }
  if (!imageAnnotationsFile && summary.includes(`${base}_image_annotations.json`)) {
    throw new Error(`the summary names ${base}_image_annotations.json but MARA did not return it`);
  }
  const structures = numbered.map((s, i) => ({
    ...s,
    name: (listed && listed[i].name) || nameFromFile(s.file, base),
    atoms: listed ? listed[i].atoms : null,
    openFrame: listed ? listed[i].openFrame : null,
  }));
  const used = new Set([componentsFile, annotationsFile, measurementsFile, metadataFile, imageAnnotationsFile, ...structures.map(s => s.file)]);
  const unused = files.filter(f => !used.has(f) && !f.startsWith(`${base}_media_`));
  if (unused.length) warnings.push(`MARA returned files this import does not use: ${unused.join(', ')}`);
  return { base, componentsFile, annotationsFile, measurementsFile, metadataFile, imageAnnotationsFile, structures, warnings,
    description: summaryDescription(summary) };
}

/**
 * Converted mode: the outputs are named explicitly, the structure files in entry order.
 * converted: {baseUrl, files, components, annotations?, imageAnnotations?, summary?, names?,
 * nothingToImport?, scene?}; `names` (complex names, one per file) are optional: else the summary's
 * list, else the `<base>_NN_<name>` part of the name. `nothingToImport` is the converter's
 * result['nothing_to_import'] ('empty' or 'unsupported' when the session gives v2 no structure
 * file and no image, else null; the summary's 'Nothing to import:' line says why) and `scene` its
 * result['scene'] (the scene of a .nanoscenes deck converted, 1-based, else null).
 */
export function convertedOutputs(converted) {
  const { baseUrl, files, components, annotations = null, imageAnnotations = null, summary = '', names = null } = converted || {};
  const { nothingToImport, scene = null } = converted || {};
  if (typeof baseUrl !== 'string' || !/^[a-z][a-z0-9+.-]*:\/\//i.test(baseUrl)) throw new Error('converted.baseUrl must be an absolute URL');
  // a session with no structure still makes a workspace: of its images, or empty, as v1 opens it
  if (!Array.isArray(files) || files.some(f => typeof f !== 'string' || !f)) {
    throw new Error('converted.files must be a list of structure file names, in entry order (it may be empty)');
  }
  if (imageAnnotations !== null && (typeof imageAnnotations !== 'string' || !imageAnnotations)) throw new Error('converted.imageAnnotations must be a file name or null');
  if (typeof components !== 'string' || !components) throw new Error('converted.components must name the components JSON file');
  if (annotations !== null && (typeof annotations !== 'string' || !annotations)) throw new Error('converted.annotations must be a file name or null');
  if (nothingToImport !== undefined && nothingToImport !== null && !['empty', 'unsupported'].includes(nothingToImport)) {
    throw new Error(`converted.nothingToImport must be 'empty', 'unsupported' or null, not ${JSON.stringify(nothingToImport)}`);
  }
  // the converter says "nothing to import" exactly when it wrote no structure file and no image
  // (tool_main.py). Only a note if not: the import goes by the files either way
  const warnings = [];
  if (nothingToImport !== undefined && Boolean(nothingToImport) !== (!files.length && !imageAnnotations)) {
    warnings.push(nothingToImport
      ? `The converter says there is nothing to import (${nothingToImport}), but it wrote ${files.length} structure file(s)${imageAnnotations ? ' and image annotations' : ''}; importing those.`
      : 'The converter wrote no structure file and no image annotations, but does not say there is nothing to import.');
  }
  if (scene !== null && !(Number.isInteger(scene) && scene >= 1)) throw new Error(`converted.scene must be a scene number (1, 2, ...) or null, not ${JSON.stringify(scene)}`);
  const base = components.endsWith('_components.json') ? components.slice(0, -'_components.json'.length) : null;
  const listed = summaryStructureLines(summary);
  const listedMatches = listed && listed.length === files.length && listed.every((l, i) => l.file === files[i]);
  const structures = files.map((file, i) => {
    const m = /\.(pdb|cif|sdf)$/i.exec(file);
    if (!m) throw new Error(`${file}: expected a .pdb, .cif or .sdf file`);
    const given = Array.isArray(names) && typeof names[i] === 'string' && names[i] ? names[i] : null;
    return { index: i + 1, file, format: m[1].toLowerCase(), name: given || (listedMatches ? listed[i].name : nameFromFile(file, base)), atoms: listedMatches ? listed[i].atoms : null,
      openFrame: listedMatches ? listed[i].openFrame : null };
  });
  return { base, baseUrl: baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`, componentsFile: components, annotationsFile: annotations, imageAnnotationsFile: imageAnnotations, structures, warnings,
    description: summaryDescription(summary), nothingToImport: nothingToImport || null, scene };
}

/** What the tool asks the workspace description to say (tool_main.py _description: the title,
 * method and resolution of each structure's PDB / mmCIF header), from its first build step
 * "  1. Create Nanome Workspace, description: <text>.", or ''. */
export function summaryDescription(summary) {
  const m = /^\s+1\. Create Nanome Workspace, description: (.*)\.$/m.exec(String(summary || ''));
  return m ? m[1].trim() : '';
}

/** Everything the tool said after its build instructions: what was not carried over, placement,
 * interactions without a v2 equivalent, frames, measurements. Kept verbatim. */
export function summaryNotes(summary) {
  const paragraphs = String(summary || '')
    .split(/\r?\n[ \t]*\r?\n/)
    .map(p => p.trim())
    .filter(Boolean);
  const build = paragraphs.findIndex(p => p.startsWith('To build the v2 workspace:'));
  return build < 0 ? paragraphs : paragraphs.slice(build + 1);
}

// --- components and annotations -----------------------------------------------------------------

/** Filters with every entrySerial (also inside Union / Intersect / Except containedFilters)
 * replaced through `serials`, a Map from the tool's entry number (1..N) to the loaded serial. */
export function remapFilters(filters, serials, where = 'filters') {
  if (!Array.isArray(filters)) throw new Error(`${where}: expected a list of filters`);
  return filters.map((filter, i) => {
    if (!filter || typeof filter !== 'object') throw new Error(`${where}[${i}] is not a filter`);
    const out = { ...filter };
    if ('entrySerial' in filter) {
      const serial = serials.get(filter.entrySerial);
      if (serial === undefined) {
        throw new Error(`${where}[${i}] selects entry ${JSON.stringify(filter.entrySerial)}, which is not one of the ${serials.size} loaded structures`);
      }
      out.entrySerial = serial;
    }
    if ('containedFilters' in filter) {
      out.containedFilters = remapFilters(filter.containedFilters, serials, `${where}[${i}].containedFilters`);
    }
    return out;
  });
}

export function remapComponents(components, serials) {
  if (!Array.isArray(components)) throw new Error('the components file is not a JSON list');
  return components.map((component, i) => {
    if (!component || typeof component.name !== 'string') throw new Error(`component ${i} has no name`);
    if (!Array.isArray(component.filters) || !component.filters.length) throw new Error(`component ${i} (${component.name}) has no filters`);
    if (!Array.isArray(component.visualizations) || !component.visualizations.length) {
      throw new Error(`component ${i} (${component.name}) has no visualizations`);
    }
    return { ...component, filters: remapFilters(component.filters, serials, `component ${i} (${component.name}) filters`) };
  });
}

/** The body MARA's own "Add Components to Nanome Workspace Scene" posts for a component
 * a visualization without a size gets NoSize. */
export function restComponent(component) {
  return {
    ...component,
    visualizations: component.visualizations.map(v =>
      v && typeof v === 'object' && v.size === undefined ? { ...v, size: { sizeOption: 'NoSize', scale: 0 } } : v),
  };
}

/**
 * The converter writes a structure hidden in v1 as components whose visualizations are all
 * `visible: false`. v2's web app shows such a component as "No representations" and its eye icon
 * then shows nothing. v2 hides a component with its own flag instead (`hidden`, set by
 * POST .../components/toggle-hidden), which the add body cannot carry. So such a component is sent with every visualization on
 * and hidden once all are added. Returns {send, hideIndexes}: the components to add, in order, and
 * the indexes of those to hide. Any other component (one visualization on, or none at all) is sent
 * as it is.
 */
export function componentsToSend(components) {
  const hideIndexes = [];
  const send = components.map((component, i) => {
    const visualizations = component && Array.isArray(component.visualizations) ? component.visualizations : [];
    if (!visualizations.length || !visualizations.every(v => v && v.visible === false)) return component;
    hideIndexes.push(i);
    return { ...component, visualizations: visualizations.map(v => ({ ...v, visible: true })) };
  });
  return { send, hideIndexes };
}

export function remapAnnotations(annotations, serials) {
  if (!Array.isArray(annotations)) throw new Error('the annotations file is not a JSON list');
  return annotations.map((annotation, i) => {
    const anchor = annotation && annotation.anchor;
    if (!anchor || typeof anchor !== 'object') throw new Error(`annotation ${i} has no anchor`);
    const out = { ...annotation, anchor: { ...anchor } };
    if (Array.isArray(anchor.entries)) {
      out.anchor.entries = anchor.entries.map(entry => {
        const serial = serials.get(entry);
        if (serial === undefined) throw new Error(`annotation ${i} is anchored on entry ${JSON.stringify(entry)}, which was not loaded`);
        return serial;
      });
    }
    if (Array.isArray(anchor.filter)) out.anchor.filter = remapFilters(anchor.filter, serials, `annotation ${i} anchor filter`);
    return out;
  });
}

// type -> [GraphQL mutation, atoms per anchor]
const ANNOTATION_MUTATIONS = {
  distance: ['addDistanceAnnotations', 2],
  angle: ['addAngleAnnotations', 3],
  dihedralAngle: ['addDihedralAngleAnnotations', 4],
};
// EAnchorType in declaration order.
const ANCHOR_TYPES = ['Scene', 'Entry', 'Atom', 'AtomGroups', 'Filter'];

/** An enum value as REST JSON writes it ('AtomGroups' or 3) -> HotChocolate's name (ATOM_GROUPS). */
export function graphqlEnum(value, names = ANCHOR_TYPES) {
  if (Number.isInteger(value) && value >= 0 && value < names.length) value = names[value];
  if (typeof value !== 'string' || !value) throw new Error(`not an enum value: ${JSON.stringify(value)}`);
  return /^[A-Z0-9_]+$/.test(value) ? value : value.replace(/(?!^)(?=[A-Z])/g, '_').toUpperCase();
}

/**
 * Annotation JSON (the Workspace API's AnnotationModel, as the tool writes it) -> one GraphQL
 * mutation per type, like the draft MARA tool (v1-parser-tool's
 * docs/mara-add-annotations-tool.patch): drop the `type` discriminator, name the anchor type the
 * GraphQL way, and give atom anchors without model serials each entry's current model.
 * `currentModels`: Map entry serial -> model serial.
 */
export function annotationMutations(annotations, currentModels = new Map()) {
  const groups = new Map();
  annotations.forEach((annotation, i) => {
    const spec = ANNOTATION_MUTATIONS[annotation && annotation.type];
    if (!spec) throw new Error(`annotation ${i}: type ${JSON.stringify(annotation && annotation.type)} is not distance, angle or dihedralAngle`);
    const [mutation, atomCount] = spec;
    const anchor = {};
    for (const [key, value] of Object.entries(annotation.anchor || {})) {
      if (value !== null && value !== undefined) anchor[key] = value;
    }
    anchor.eAnchorType = graphqlEnum(anchor.eAnchorType === undefined ? 'Atom' : anchor.eAnchorType);
    if (!anchor.offset) anchor.offset = { x: 0, y: 0, z: 0 };
    if (anchor.eAnchorType === 'ATOM') {
      const { entries, atoms } = anchor;
      if (!Array.isArray(entries) || !Array.isArray(atoms) || entries.length !== atoms.length || atoms.length !== atomCount) {
        throw new Error(`annotation ${i}: a ${annotation.type} anchor needs ${atomCount} atoms, each with its entry`);
      }
      if (!Array.isArray(anchor.models)) {
        anchor.models = entries.map(entry => {
          const model = currentModels.get(entry);
          if (model === undefined) throw new Error(`annotation ${i}: entry ${entry} is not in the scene`);
          return model;
        });
      }
      if (anchor.models.length !== atoms.length) throw new Error(`annotation ${i}: ${anchor.models.length} models for ${atoms.length} atoms`);
    }
    if (!groups.has(mutation)) groups.set(mutation, []);
    groups.get(mutation).push({ serial: 0, anchor }); // the server numbers annotations itself
  });
  return [...groups].map(([mutation, inputs]) => ({ mutation, inputs }));
}

/** HotChocolate mutation conventions: one `input: <Name>Input!` argument, errors in the payload. */
export function annotationMutationQuery(mutation) {
  const name = mutation[0].toUpperCase() + mutation.slice(1);
  return `mutation ${name}($input: ${name}Input!) { ${mutation}(input: $input) { errors { ... on Error { message } } } }`;
}

export function graphqlErrors(body, mutation) {
  if (!body || typeof body !== 'object') return ['the response is not a GraphQL result'];
  const errors = (Array.isArray(body.errors) ? body.errors : []).map(e => (e && e.message) || JSON.stringify(e));
  const payload = body.data && body.data[mutation];
  if (payload && Array.isArray(payload.errors)) errors.push(...payload.errors.map(e => (e && e.message) || JSON.stringify(e)));
  if (!errors.length && !payload) errors.push(`no ${mutation} result in the response`);
  return errors;
}

// --- multipart bodies -------------------------------------------------------------------------------

function toBlob(deps, bytes) {
  return bytes instanceof deps.Blob ? bytes : new deps.Blob([bytes]);
}

/** POST /api/tools/{id}/run: `args` is a JSON string, and each file argument is a part named after
 * the argument whose file name is also the argument's value. */
export function toolRunForm(deps, { bytes, uploadName, args = {} }) {
  const form = new deps.FormData();
  form.append('args', JSON.stringify({ ...args, input_file: uploadName }));
  form.append('input_file', toBlob(deps, bytes), uploadName);
  return form;
}

/** POST /workspaces/{id}/entries/load-multiple: every file as a `files` part, in load order; the
 * API loads them in that order. The import sends one file each. */
export function loadForm(deps, files) {
  const form = new deps.FormData();
  for (const file of files) form.append('files', toBlob(deps, file.bytes), file.name);
  return form;
}

// --- structure files: what v2 should store for them --------------------------------------------------
//
// Each parser returns models [{serial, atoms: [{serial, x, y, z, element, charge}], bonds:
// [{a, b, kind}], allBonds}], numbered the way v2 numbers them. Bonds are pairs of atom serials
// (a < b) with v2's kinds: 1 single, 2 double, 3 triple, 4 aromatic. allBonds:
// the file lists every bond (SDF); PDB and mmCIF list only some and v2 perceives the rest.

const ELEMENTS = (
  'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr ' +
  'Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb ' +
  'Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf ' +
  'Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'
).split(' ');

/** 'ZN', 'Zn', 'zn' -> 30; anything else (blank, X, a name) -> null. */
export function atomicNumber(symbol) {
  const text = typeof symbol === 'string' ? symbol.trim() : '';
  if (!text) return null;
  return ELEMENTS.indexOf(text[0].toUpperCase() + text.slice(1).toLowerCase()) + 1 || null;
}

/** {a, b, kind} pairs -> one per pair, a < b, sorted; the last kind given for a pair wins. */
function bondList(bonds) {
  const byPair = new Map();
  for (const { a, b, kind } of bonds) {
    if (!Number.isInteger(a) || !Number.isInteger(b) || a === b) continue;
    byPair.set(a < b ? `${a}-${b}` : `${b}-${a}`, { a: Math.min(a, b), b: Math.max(a, b), kind });
  }
  return [...byPair.values()].sort((p, q) => p.a - q.a || p.b - q.b);
}

/** Columns 79-80 of a PDB atom line: "2+" -> 2, "1-" -> -1, blank -> null. */
function pdbCharge(text) {
  const t = text.trim();
  if (!/^\d[+-]$/.test(t) && !/^[+-]\d$/.test(t)) return null;
  const digit = Number(t.replace(/[+-]/, ''));
  return t.includes('-') ? -digit : digit;
}

/** PDB -> models. Model serials come from MODEL records, 1 without any. CONECT pairs are bonds whose order is how often the pair is listed in its
 * more frequent direction, never aromatic; a model takes the pairs whose two serials it holds, as
 * v2 does. */
export function parsePdbModels(text) {
  const models = [];
  const listed = new Map(); // "a b" -> times b is listed on a's CONECT lines
  let current = null;
  for (const line of text.split(/\r?\n/)) {
    const record = line.slice(0, 6);
    if (record === 'MODEL ') {
      const serial = parseInt(line.slice(6, 14), 10);
      current = { serial: Number.isFinite(serial) ? serial : models.length + 1, atoms: [] };
      models.push(current);
    } else if (record === 'ATOM  ' || record === 'HETATM') {
      if (!current) {
        current = { serial: models.length + 1, atoms: [] };
        models.push(current);
      }
      current.atoms.push({
        serial: parseInt(line.slice(6, 11), 10),
        x: parseFloat(line.slice(30, 38)),
        y: parseFloat(line.slice(38, 46)),
        z: parseFloat(line.slice(46, 54)),
        element: line.slice(76, 78).trim() || null,
        charge: pdbCharge(line.slice(78, 80)),
      });
    } else if (record === 'ENDMDL') {
      current = null;
    } else if (record === 'CONECT') {
      const a = parseInt(line.slice(6, 11), 10);
      for (let p = 11; p < 31; p += 5) {
        const b = parseInt(line.slice(p, p + 5), 10);
        if (Number.isFinite(a) && Number.isFinite(b)) listed.set(`${a} ${b}`, (listed.get(`${a} ${b}`) || 0) + 1);
      }
    }
  }
  const bonds = [];
  for (const [key, count] of listed) {
    const [a, b] = key.split(' ').map(Number);
    const times = Math.max(count, listed.get(`${b} ${a}`) || 0);
    bonds.push({ a, b, kind: times === 2 ? 2 : times === 3 ? 3 : 1 });
  }
  const list = bondList(bonds);
  for (const model of models) {
    const present = new Set(model.atoms.map(a => a.serial));
    Object.assign(model, { bonds: list.filter(b => present.has(b.a) && present.has(b.b)), allBonds: false });
  }
  return models;
}

/** One line of CIF values: whitespace-separated, 'quoted' or "quoted" (a quote closes only when
 * followed by whitespace), # starts a comment. */
export function cifTokens(line) {
  const tokens = [];
  let i = 0;
  while (i < line.length) {
    while (i < line.length && /\s/.test(line[i])) i++;
    if (i >= line.length || line[i] === '#') break;
    const quote = line[i];
    if (quote === "'" || quote === '"') {
      let j = i + 1;
      while (j < line.length && !(line[j] === quote && (j + 1 === line.length || /\s/.test(line[j + 1])))) j++;
      tokens.push(line.slice(i + 1, j));
      i = j + 1;
    } else {
      let j = i;
      while (j < line.length && !/\s/.test(line[j])) j++;
      tokens.push(line.slice(i, j));
      i = j;
    }
  }
  return tokens;
}

/** Every loop_ of an mmCIF file: {category: {columns, rows}}, e.g. loops.atom_site. */
export function cifLoops(text) {
  const lines = text.split(/\r?\n/);
  const loops = {};
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() !== 'loop_') continue;
    const names = [];
    let j = i + 1;
    while (j < lines.length && lines[j].trim().startsWith('_')) names.push(lines[j++].trim());
    if (!names.length) continue;
    const category = names[0].slice(1, names[0].indexOf('.'));
    const columns = names.map(n => n.slice(n.indexOf('.') + 1));
    const rows = [];
    let values = [];
    for (; j < lines.length; j++) {
      const trimmed = lines[j].trim();
      if (!trimmed) continue;
      if (trimmed.startsWith('#') || trimmed === 'loop_' || trimmed.startsWith('_') || trimmed.startsWith('data_')) break;
      if (lines[j].startsWith(';')) throw new Error(`multi-line text values in _${category} are not supported`);
      values.push(...cifTokens(lines[j]));
      while (values.length >= columns.length) {
        rows.push(values.slice(0, columns.length));
        values = values.slice(columns.length);
      }
    }
    if (values.length) throw new Error(`_${category} ends with ${values.length} stray value(s)`);
    loops[category] = { columns, rows };
    i = j - 1;
  }
  return loops;
}

// v2's bond orders for _struct_conn.pdbx_value_order and _chem_comp_bond.value_order: exactly
// 'doub' and 'trip', anything else single.
const CIF_V2_ORDERS = { doub: 2, trip: 3 };
const cifValue = value => (value === undefined || value === '?' || value === '.' ? null : value);
const isLetter = ch => typeof ch === 'string' && /^\p{L}$/u.test(ch);
/** An atom_site insertion code as v2 reads it: the first letter anywhere in the value, else none
 * ('?' and '.' hold none). */
const cifInsertion = value => [...String(value ?? '')].find(isLetter) || '';
/** A _struct_conn insertion code as v2 reads it: the value's first character when that is a
 * letter, else none. */
const connInsertion = value => (isLetter(String(value ?? '')[0]) ? String(value)[0] : '');
/** An integer as v2 reads one: an optional sign and digits, blanks around allowed; null otherwise. */
const cifInt = value => (/^\s*[+-]?\d+\s*$/.test(String(value ?? '')) ? parseInt(value, 10) : null);
const residueKey = (chain, number, code) => JSON.stringify([chain, number, code]);

/**
 * mmCIF -> models by pdbx_PDB_model_num (1 without the column), with the bonds v2 takes from the
 * file, per model (v1-parser-tool's tests/v2_mmcif.py does the same in Python):
 * - atoms are named by the auth_* columns when atom_site has all four (atom, residue number,
 *   residue name, chain), every auth_seq_id is an integer and no auth atom, residue or chain name
 *   is blank; else by the label_* ones, the residue number from pdbe_label_seq_id when there is
 *   one, '.' read as 0;
 * - _struct_conn rows of conn_type 'covale' or 'disulf' join two atoms found by chain, residue
 *   number (auth or label, like the atoms), insertion code and ptnr*_label_atom_id: v2 lists a
 *   residue's atoms from where the chain or the number changes in file order (so a residue that
 *   differs from the one before it only by insertion code joins that one's list, and its own key
 *   finds nothing), and takes the FIRST atom of that name in the list. Order 'doub' 2, 'trip' 3,
 *   anything else 1, never aromatic;
 * - _chem_comp_bond rows (only small-molecule files still have them) bind, in every residue of
 *   that name grouped by residue number alone, the first atom of each name; aromatic (4) when
 *   pdbx_aromatic_flag is 'Y'. With such a table v2 drops a repeat of a bond listed with its
 *   atoms in the same order.
 * A pair v2 still holds twice keeps the kind listed last, as compareModel reads v2's bonds back.
 */
export function parseMmcifModels(text) {
  const loops = cifLoops(text);
  const site = loops.atom_site;
  if (!site) throw new Error('no _atom_site loop');
  const column = (...names) => names.map(n => site.columns.indexOf(n)).find(i => i >= 0) ?? -1;
  const blank = value => value === undefined || !String(value).trim();
  const authColumns = ['auth_atom_id', 'auth_seq_id', 'auth_comp_id', 'auth_asym_id'].map(n => site.columns.indexOf(n));
  // v2 takes the auth names only when all four read cleanly, and then reads _struct_conn by auth
  // too
  const auth = authColumns.every(i => i >= 0) && site.rows.every(row =>
    cifInt(row[authColumns[1]]) !== null && [0, 2, 3].every(k => !blank(row[authColumns[k]])));
  const naming = name => column(`${auth ? 'auth' : 'label'}_${name}`);
  const c = {
    id: column('id'), x: column('Cartn_x'), y: column('Cartn_y'), z: column('Cartn_z'), model: column('pdbx_PDB_model_num'),
    element: column('type_symbol'), charge: column('pdbx_formal_charge'), atom: naming('atom_id'),
    comp: naming('comp_id'), chain: naming('asym_id'), seq: auth ? column('auth_seq_id') : column('pdbe_label_seq_id', 'label_seq_id'),
    ins: column('pdbx_PDB_ins_code'),
  };
  if (c.id < 0 || c.x < 0 || c.y < 0 || c.z < 0) throw new Error('_atom_site has no id / Cartn_x / Cartn_y / Cartn_z');
  const models = new Map();
  for (const row of site.rows) {
    const serial = c.model < 0 ? 1 : parseInt(row[c.model], 10);
    if (!models.has(serial)) models.set(serial, { serial, atoms: [], names: [], comps: [], chains: [], numbers: [], codes: [] });
    const model = models.get(serial);
    const charge = c.charge < 0 ? null : cifValue(row[c.charge]);
    model.atoms.push({
      serial: parseInt(row[c.id], 10), x: parseFloat(row[c.x]), y: parseFloat(row[c.y]), z: parseFloat(row[c.z]),
      element: c.element < 0 ? null : cifValue(row[c.element]), charge: charge === null ? null : parseInt(charge, 10),
    });
    model.names.push(row[c.atom]);
    model.comps.push(row[c.comp]);
    model.chains.push(row[c.chain]);
    // label numbers: '.' (no residue number) is 0
    const number = !auth && row[c.seq] === '.' ? 0 : cifInt(row[c.seq]);
    model.numbers.push(number === null ? row[c.seq] : number);
    model.codes.push(c.ins < 0 ? '' : cifInsertion(row[c.ins]));
  }

  // _struct_conn: [[chain, number, insertion code, atom name] x 2, kind]
  const links = [];
  const conn = loops.struct_conn;
  if (conn) {
    const at = name => conn.columns.indexOf(name);
    const side = auth ? 'auth' : 'label';
    const need = ['conn_type_id', `ptnr1_${side}_asym_id`, `ptnr2_${side}_asym_id`, `ptnr1_${side}_seq_id`, `ptnr2_${side}_seq_id`,
      'ptnr1_label_atom_id', 'ptnr2_label_atom_id'];
    if (need.every(name => at(name) >= 0)) {
      const order = at('pdbx_value_order');
      for (const row of conn.rows) {
        const type = row[at('conn_type_id')];
        if (type !== 'covale' && type !== 'disulf') continue;
        const ends = [1, 2].map(n => {
          const code = at(`pdbx_ptnr${n}_PDB_ins_code`);
          return [row[at(`ptnr${n}_${side}_asym_id`)], cifInt(row[at(`ptnr${n}_${side}_seq_id`)]),
            code < 0 ? '' : connInsertion(row[code]), row[at(`ptnr${n}_label_atom_id`)]];
        });
        if (ends[0][1] === null || ends[1][1] === null) continue; // v2 skips a row whose residue number is no integer
        links.push([ends[0], ends[1], (order >= 0 && CIF_V2_ORDERS[row[order]]) || 1]);
      }
    }
  }

  // _chem_comp_bond: residue name -> [[atom name, atom name, kind]], in the table's order; null
  // without a complete table (v2 then applies none and keeps repeats)
  let templates = null;
  const chem = loops.chem_comp_bond;
  if (chem) {
    const at = name => chem.columns.indexOf(name);
    if (['comp_id', 'atom_id_1', 'atom_id_2', 'value_order', 'pdbx_aromatic_flag'].every(name => at(name) >= 0)) {
      templates = new Map();
      for (const row of chem.rows) {
        const comp = row[at('comp_id')];
        if (!templates.has(comp)) templates.set(comp, []);
        templates.get(comp).push([row[at('atom_id_1')], row[at('atom_id_2')],
          row[at('pdbx_aromatic_flag')] === 'Y' ? 4 : CIF_V2_ORDERS[row[at('value_order')]] || 1]);
      }
    }
  }

  return [...models.values()].map(({ serial, atoms, names, comps, chains, numbers, codes }) => {
    const index = new Map(); // residue key -> atom indexes, a list starting where chain or number changes
    let current = null;
    for (let i = 0; i < atoms.length; i++) {
      if (current === null || chains[i] !== chains[i - 1] || numbers[i] !== numbers[i - 1]) {
        const key = residueKey(chains[i], numbers[i], codes[i]);
        if (!index.has(key)) index.set(key, []);
        current = index.get(key);
      }
      current.push(i);
    }
    const firstOf = new Map(); // residue key -> atom name -> the first atom of that name in its list
    const find = ([chain, number, code, name]) => {
      const key = residueKey(chain, number, code);
      if (!firstOf.has(key)) {
        const byName = new Map();
        for (const k of index.get(key) || []) if (!byName.has(names[k])) byName.set(names[k], k);
        firstOf.set(key, byName);
      }
      const i = firstOf.get(key).get(name);
      return i === undefined ? null : i;
    };
    let found = []; // [atom index, atom index, kind], as v2 lists them
    for (const [end1, end2, kind] of links) {
      const i = find(end1);
      const j = find(end2);
      if (i !== null && j !== null) found.push([i, j, kind]);
    }
    if (templates) {
      const byName = new Map(); // residue name -> residue number -> atom indexes
      for (let i = 0; i < atoms.length; i++) {
        if (!byName.has(comps[i])) byName.set(comps[i], new Map());
        const groups = byName.get(comps[i]);
        if (!groups.has(numbers[i])) groups.set(numbers[i], []);
        groups.get(numbers[i]).push(i);
      }
      for (const [comp, bonds] of templates) {
        for (const [name1, name2, kind] of bonds) {
          for (const group of (byName.get(comp) || new Map()).values()) {
            const i = group.find(k => names[k] === name1);
            const j = group.find(k => names[k] === name2);
            if (i !== undefined && j !== undefined) found.push([i, j, kind]);
          }
        }
      }
      const seen = new Set();
      found = found.filter(([i, j]) => !seen.has(`${i} ${j}`) && seen.add(`${i} ${j}`));
    }
    const byPair = new Map();
    for (const [i, j, kind] of found) {
      const a = atoms[i].serial;
      const b = atoms[j].serial;
      if (!Number.isInteger(a) || !Number.isInteger(b) || a === b) continue;
      // v2 keeps both bonds of a pair listed twice; the read-back (compareModel) keeps the last
      byPair.set(a < b ? `${a}-${b}` : `${b}-${a}`, { a: Math.min(a, b), b: Math.max(a, b), kind });
    }
    const bonds = [...byPair.values()].sort((p, q) => p.a - q.a || p.b - q.b);
    return { serial, atoms, bonds, allBonds: false };
  });
}

// V2000 atom-line charge codes; 4 is a doublet radical.
const V2000_CHARGES = { 0: 0, 1: 3, 2: 2, 3: 1, 4: 0, 5: -1, 6: -2, 7: -3 };

function sdfV2000(record, n) {
  const atomCount = parseInt(record[3].slice(0, 3), 10);
  const bondCount = parseInt(record[3].slice(3, 6), 10);
  if (!Number.isFinite(atomCount) || !Number.isFinite(bondCount)) throw new Error(`record ${n} has no counts line: ${JSON.stringify(record[3])}`);
  const atoms = [];
  const bonds = [];
  for (let k = 0; k < atomCount; k++) {
    const line = record[4 + k];
    if (line === undefined) throw new Error(`record ${n} ends before its ${atomCount} atoms`);
    atoms.push({
      serial: k + 1,
      x: parseFloat(line.slice(0, 10)),
      y: parseFloat(line.slice(10, 20)),
      z: parseFloat(line.slice(20, 30)),
      element: line.slice(31, 34).trim(),
      charge: V2000_CHARGES[parseInt(line.slice(36, 39), 10) || 0] ?? 0,
    });
  }
  for (let k = 0; k < bondCount; k++) {
    const line = record[4 + atomCount + k];
    if (line === undefined) throw new Error(`record ${n} ends before its ${bondCount} bonds`);
    bonds.push({ a: parseInt(line.slice(0, 3), 10), b: parseInt(line.slice(3, 6), 10), kind: parseInt(line.slice(6, 9), 10) });
  }
  // M  CHG sets the charges of the atoms it lists.
  for (const line of record.slice(4 + atomCount + bondCount)) {
    if (line.startsWith('M  END')) break;
    if (!line.startsWith('M  CHG')) continue;
    const values = line.slice(6).trim().split(/\s+/).map(Number);
    for (let k = 1; k + 1 < values.length; k += 2) {
      if (atoms[values[k] - 1]) atoms[values[k] - 1].charge = values[k + 1];
    }
  }
  return { atoms, bonds };
}

function sdfV3000(lines) {
  const atoms = [];
  const bonds = [];
  let section = null;
  let pending = '';
  for (const line of lines) {
    if (line.startsWith('M  END')) break;
    if (!line.startsWith('M  V30 ')) continue;
    let content = pending + line.slice(7);
    if (content.endsWith('-')) {
      pending = content.slice(0, -1);
      continue;
    }
    pending = '';
    content = content.trim();
    const begin = /^BEGIN (\w+)/.exec(content);
    if (begin) section = begin[1];
    else if (/^END \w+/.test(content)) section = null;
    else if (section === 'ATOM') {
      const [index, symbol, x, y, z, , ...properties] = content.split(/\s+/);
      const charge = properties.find(p => p.startsWith('CHG='));
      atoms.push({ serial: parseInt(index, 10), x: parseFloat(x), y: parseFloat(y), z: parseFloat(z), element: symbol, charge: charge ? parseInt(charge.slice(4), 10) : 0 });
    } else if (section === 'BOND') {
      const [, kind, a, b] = content.split(/\s+/);
      bonds.push({ a: parseInt(a, 10), b: parseInt(b, 10), kind: parseInt(kind, 10) });
    }
  }
  return { atoms, bonds };
}

/** SDF -> one model per record, serial 1, 2, ... An atom's serial is its position in a V2000
 * record and the index written on a V3000 atom line. v2 bonds exactly what the file lists, so
 * allBonds is true. */
export function parseSdfModels(text) {
  const lines = text.split(/\r?\n/);
  const models = [];
  let start = 0;
  while (start < lines.length) {
    let end = start;
    while (end < lines.length && lines[end].trim() !== '$$$$') end++;
    const record = lines.slice(start, end);
    start = end + 1;
    if (!record.some(line => line.trim())) continue; // blank lines after the last $$$$
    const n = models.length + 1;
    if (record.length < 4) throw new Error(`record ${n} is too short`);
    const { atoms, bonds } = record[3].includes('V3000') ? sdfV3000(record.slice(4)) : sdfV2000(record, n);
    const ctabEnd = record.findIndex(line => line.startsWith('M  END'));
    models.push({ serial: n, atoms, bonds: bondList(bonds), allBonds: true, title: record[0],
      data: ctabEnd < 0 ? {} : sdfDataItems(record.slice(ctabEnd + 1)) });
  }
  return models;
}

/** An SDF record's data items the way v2's SdfParser reads them (AcceptNonStructuralData):
 * a '>' line names the item by the text between its first '<' and last '>', the lines up to the
 * next empty one are its value. */
export function sdfDataItems(lines) {
  const data = {};
  let key = null;
  let values = [];
  for (const line of lines) {
    if (key === null) {
      if (line === '' || !line.startsWith('>')) continue;
      const begin = line.indexOf('<');
      const end = line.lastIndexOf('>');
      if (begin < 0 || end < 0) continue;
      key = line.slice(begin + 1, end);
      values = [];
    } else if (line === '') {
      data[key] = values;
      key = null;
    } else {
      values.push(line);
    }
  }
  return data;
}

/** The metadata v2 keeps for an SDF record: its data items, with the record's title first in the
 * item named Name (any case), which v2 adds when there is none. */
export function v2SdfMetadata(model) {
  const data = { ...model.data };
  const nameKey = Object.keys(data).find(k => k.toLowerCase() === 'name') || 'Name';
  data[nameKey] = [model.title, ...(data[nameKey] || []).filter(v => v !== model.title)];
  return data;
}

export function parseStructure(text, format) {
  if (format === 'pdb') return parsePdbModels(text);
  if (format === 'cif') return parseMmcifModels(text);
  if (format === 'sdf') return parseSdfModels(text);
  throw new Error(`unknown structure format ${format}`);
}

/** Up to `count` indices into a list of `length`, always the first and the last, evenly spread. */
export function sampleIndices(length, count) {
  if (length <= 0 || count <= 0) return [];
  if (count >= length) return Array.from({ length }, (_, i) => i);
  if (count === 1) return [0];
  const picked = new Set();
  for (let k = 0; k < count; k++) picked.add(Math.round((k * (length - 1)) / (count - 1)));
  return [...picked].sort((a, b) => a - b);
}

// --- comparing a model with what v2 stored ------------------------------------------------------------

const PDB_CHARGES_IGNORED =
  'v2 ignores the charge columns of a PDB file and works out ligand and ion charges itself';
const listing = values => values.slice(0, EXAMPLES).join(', ') + (values.length > EXAMPLES ? `, and ${values.length - EXAMPLES} more` : '');

/**
 * One model of a converted file (parseStructure) against the ModelModel JSON v2 stored for it
 * (GET /workspaces/{ws}/entries/{e}/models/{m}): atomSerial[], coordinates
 * {x[], y[], z[]}, atomicNumber[], formalCharge[], bonding {atom1[], atom2[], kind[],
 * kekulizedKind[]} with atom1/atom2 indices into the arrays.
 *
 * Every atom is compared. `problems` fail the verification; `notes` are differences v2 makes by
 * design (it works out PDB charges, marks flat rings aromatic, gives charges the file left out).
 * `full` adds `stored`, v2's arrays with bonds as serial pairs, for offline analysis.
 */
export function compareModel(expected, stored, { samples = DEFAULTS.verifyAtoms, tolerance = DEFAULTS.tolerance, format = null, full = false } = {}) {
  const problems = [];
  const notes = [];
  const s = stored && typeof stored === 'object' ? stored : {};
  const serials = Array.isArray(s.atomSerial) ? s.atomSerial : [];
  const coordinates = s.coordinates && Array.isArray(s.coordinates.x) && Array.isArray(s.coordinates.y) && Array.isArray(s.coordinates.z) ? s.coordinates : null;
  const indexOf = new Map(serials.map((serial, i) => [serial, i]));
  const inFile = new Set(expected.atoms.map(a => a.serial));

  if (serials.length !== expected.atoms.length) problems.push(`${serials.length} atoms in v2, ${expected.atoms.length} in the file`);
  const missing = expected.atoms.filter(a => !indexOf.has(a.serial)).map(a => a.serial);
  const extra = serials.filter(serial => !inFile.has(serial));
  if (missing.length) problems.push(`${missing.length} atom(s) of the file are not in v2: ${listing(missing)}`);
  if (extra.length) problems.push(`${extra.length} atom(s) in v2 are not in the file: ${listing(extra)}`);
  if (serials.length && !coordinates) problems.push('v2 returned no coordinates');

  // Coordinates of every atom both hold.
  const coords = { compared: 0, outside: 0, maxDeviation: 0, worst: [] };
  if (coordinates) {
    for (const atom of expected.atoms) {
      const i = indexOf.get(atom.serial);
      if (i === undefined) continue;
      const v2 = [coordinates.x[i], coordinates.y[i], coordinates.z[i]];
      const deviation = Math.max(Math.abs(v2[0] - atom.x), Math.abs(v2[1] - atom.y), Math.abs(v2[2] - atom.z));
      coords.compared++;
      if (!(deviation <= tolerance)) coords.outside++;
      const rank = Number.isFinite(deviation) ? deviation : Infinity;
      if (coords.worst.length < 5 || rank > coords.worst[coords.worst.length - 1].deviation) {
        coords.worst.push({ serial: atom.serial, file: [atom.x, atom.y, atom.z], v2, deviation: rank });
        coords.worst.sort((p, q) => q.deviation - p.deviation);
        coords.worst.length = Math.min(coords.worst.length, 5);
      }
      coords.maxDeviation = Math.max(coords.maxDeviation, rank);
    }
    if (coords.outside) {
      const w = coords.worst[0];
      problems.push(`${coords.outside} atom(s) are more than ${tolerance} A from the file; the worst, atom ${w.serial}, is at (${w.v2.join(', ')}) in v2, (${w.file.join(', ')}) in the file`);
    }
  }

  // Elements: the file's symbol against v2's atomic number (atoms whose element the file leaves
  // blank are left out: v2 guesses those from the atom name).
  const elements = { compared: 0, mismatches: 0, examples: [] };
  if (Array.isArray(s.atomicNumber)) {
    for (const atom of expected.atoms) {
      const i = indexOf.get(atom.serial);
      const z = atomicNumber(atom.element);
      if (i === undefined || z === null) continue;
      elements.compared++;
      if (s.atomicNumber[i] === z) continue;
      elements.mismatches++;
      if (elements.examples.length < EXAMPLES) elements.examples.push({ serial: atom.serial, file: atom.element, fileAtomicNumber: z, v2: s.atomicNumber[i] });
    }
    if (elements.mismatches) problems.push(`${elements.mismatches} element(s) differ: ${elements.examples.map(e => `atom ${e.serial} ${e.file} (${e.fileAtomicNumber}) is ${e.v2} in v2`).join('; ')}`);
  } else if (serials.length) {
    notes.push('v2 returned no atomic numbers');
  }

  // Formal charges.
  const charges = { compared: 0, mismatches: 0, assignedByV2: 0, examples: [] };
  if (Array.isArray(s.formalCharge)) {
    for (const atom of expected.atoms) {
      const i = indexOf.get(atom.serial);
      if (i === undefined) continue;
      const file = atom.charge === undefined ? null : atom.charge;
      const v2 = s.formalCharge[i] === undefined ? null : s.formalCharge[i];
      charges.compared++;
      if (file === v2) continue;
      if (file === null) {
        charges.assignedByV2++;
        continue;
      }
      charges.mismatches++;
      if (charges.examples.length < EXAMPLES) charges.examples.push({ serial: atom.serial, file, v2 });
    }
    if (charges.mismatches) {
      const text = `${charges.mismatches} formal charge(s) differ: ${charges.examples.map(e => `atom ${e.serial} ${e.file} in the file, ${e.v2} in v2`).join('; ')}`;
      if (format === 'pdb') notes.push(`${text} (${PDB_CHARGES_IGNORED})`);
      else problems.push(text);
    }
    if (charges.assignedByV2) notes.push(`v2 gave a formal charge to ${charges.assignedByV2} atom(s) the file gives none`);
  } else if (serials.length) {
    notes.push('v2 returned no formal charges');
  }

  // Bonds the file gives, with their kinds.
  const bonds = { file: expected.bonds ? expected.bonds.length : 0, v2: 0, matched: 0, missing: 0, kindMismatches: 0, aromatized: 0, extra: null, examples: [] };
  const b = s.bonding;
  const storedBonds = new Map();
  if (b && Array.isArray(b.atom1) && Array.isArray(b.atom2) && Array.isArray(b.kind)) {
    for (let k = 0; k < b.atom1.length; k++) {
      const a1 = serials[b.atom1[k]];
      const a2 = serials[b.atom2[k]];
      storedBonds.set(a1 < a2 ? `${a1}-${a2}` : `${a2}-${a1}`, { kind: b.kind[k], kekulized: Array.isArray(b.kekulizedKind) ? b.kekulizedKind[k] : 0 });
    }
    bonds.v2 = storedBonds.size;
    const seen = new Set();
    for (const bond of expected.bonds || []) {
      const key = `${bond.a}-${bond.b}`;
      seen.add(key);
      const got = storedBonds.get(key);
      if (!got) {
        bonds.missing++;
        if (bonds.examples.length < EXAMPLES) bonds.examples.push({ a: bond.a, b: bond.b, file: bond.kind, v2: null });
      } else if (got.kind === bond.kind) {
        bonds.matched++;
      } else if (got.kind === 4 && (bond.kind === 1 || bond.kind === 2) && got.kekulized === bond.kind) {
        bonds.aromatized++; // v2 marks bonds of flat 5- and 6-rings aromatic, keeping the order
      } else {
        bonds.kindMismatches++;
        if (bonds.examples.length < EXAMPLES) bonds.examples.push({ a: bond.a, b: bond.b, file: bond.kind, v2: got.kind, kekulized: got.kekulized });
      }
    }
    if (expected.allBonds) {
      const extraBonds = [...storedBonds.keys()].filter(key => !seen.has(key));
      bonds.extra = extraBonds.length;
      if (extraBonds.length) problems.push(`${extraBonds.length} bond(s) in v2 are not in the file: ${listing(extraBonds)}`);
    }
    const shown = bonds.examples.map(e => `${e.a}-${e.b} ${e.file} in the file, ${e.v2 === null ? 'none' : e.v2} in v2`).join('; ');
    if (bonds.missing || bonds.kindMismatches) problems.push(`${bonds.missing} bond(s) of the file are not in v2 and ${bonds.kindMismatches} have another kind: ${shown}`);
    if (bonds.aromatized) notes.push(`v2 made ${bonds.aromatized} bond(s) of the file aromatic, keeping their order as the kekulized kind`);
  } else if (serials.length && bonds.file) {
    notes.push('v2 returned no bonding');
  }

  // An SDF record's data items (v1's Frames > Meta Data for that frame) against the metadata v2
  // stored for the model: every item, line for line, and nothing else.
  const metadata = { items: 0, matched: 0, missing: [], differ: [], extra: [] };
  if (format === 'sdf' && expected.data) {
    const want = v2SdfMetadata(expected);
    const got = s.metaData && typeof s.metaData === 'object' ? s.metaData : {};
    for (const [key, lines] of Object.entries(want)) {
      metadata.items++;
      if (!Array.isArray(got[key])) metadata.missing.push(key);
      else if (got[key].length !== lines.length || got[key].some((v, i) => v !== lines[i])) metadata.differ.push(key);
      else metadata.matched++;
    }
    metadata.extra = Object.keys(got).filter(key => !(key in want));
    if (metadata.missing.length) problems.push(`${metadata.missing.length} data item(s) of the file are not in v2's metadata: ${listing(metadata.missing)}`);
    if (metadata.differ.length) problems.push(`${metadata.differ.length} data item(s) hold other values in v2: ${listing(metadata.differ)}`);
    if (metadata.extra.length) problems.push(`${metadata.extra.length} metadata item(s) in v2 are not in the file: ${listing(metadata.extra)}`);
  }

  // A few atoms side by side.
  const sample = sampleIndices(expected.atoms.length, samples).map(k => {
    const atom = expected.atoms[k];
    const i = indexOf.get(atom.serial);
    return {
      serial: atom.serial,
      file: { x: atom.x, y: atom.y, z: atom.z, element: atom.element, charge: atom.charge },
      v2: i === undefined ? null : {
        x: coordinates ? coordinates.x[i] : null, y: coordinates ? coordinates.y[i] : null, z: coordinates ? coordinates.z[i] : null,
        atomicNumber: Array.isArray(s.atomicNumber) ? s.atomicNumber[i] : null,
        formalCharge: Array.isArray(s.formalCharge) ? s.formalCharge[i] : null,
      },
    };
  });

  const result = {
    ok: problems.length === 0,
    serial: expected.serial,
    expectedAtoms: expected.atoms.length,
    storedAtoms: serials.length,
    checked: coords.compared,
    maxDeviation: coords.maxDeviation,
    missing: { count: missing.length, examples: missing.slice(0, EXAMPLES) },
    extra: { count: extra.length, examples: extra.slice(0, EXAMPLES) },
    coordinates: coords,
    elements,
    charges,
    bonds,
    metadata,
    sample,
    problems,
    notes,
  };
  if (full) {
    result.stored = {
      atomSerial: serials,
      atomicNumber: s.atomicNumber || null,
      formalCharge: s.formalCharge || null,
      x: coordinates ? coordinates.x : null,
      y: coordinates ? coordinates.y : null,
      z: coordinates ? coordinates.z : null,
      bonds: [...storedBonds].map(([key, value]) => [...key.split('-').map(Number), value.kind, value.kekulized]),
    };
  }
  return result;
}

// --- HTTP --------------------------------------------------------------------------------------------

async function bodyText(res) {
  try {
    return (await res.text()).slice(0, MAX_BODY);
  } catch (e) {
    return `(could not read the response body: ${e && e.message})`;
  }
}

/**
 * The tool's `<base>_image_annotations.json` (v1's images and PDF pages): checked and turned into
 * the Workspace API's create bodies, entry anchors remapped like the other annotations. Each item:
 * {file, title, visible, targetWidth (A, v2 takes (0, 500]), anchor {eAnchorType Scene|Entry, offset,
 * entries?}}. Returns [{file, mime, body}] in the tool's order.
 */
export function imageAnnotationRequests(list, serials) {
  if (!Array.isArray(list)) throw new Error('the image annotations file is not a JSON list');
  return list.map((a, i) => {
    const where = `image annotation ${i + 1}`;
    if (!a || typeof a !== 'object') throw new Error(`${where} is not an object`);
    if (typeof a.file !== 'string' || !/\.(png|jpe?g)$/i.test(a.file)) throw new Error(`${where} names no PNG or JPEG file`);
    if (typeof a.title !== 'string') throw new Error(`${where} has no title`);
    if (!(typeof a.targetWidth === 'number' && a.targetWidth > 0 && a.targetWidth <= 500)) throw new Error(`${where}: targetWidth ${a.targetWidth} is not in (0, 500]`);
    const anchor = a.anchor || {};
    if (!['Scene', 'Entry'].includes(anchor.eAnchorType)) throw new Error(`${where}: anchor type ${anchor.eAnchorType} is not Scene or Entry`);
    const [remapped] = remapAnnotations([{ anchor }], serials);
    return {
      file: a.file,
      mime: /\.png$/i.test(a.file) ? 'image/png' : 'image/jpeg',
      body: { serial: 0, anchor: remapped.anchor, targetWidth: a.targetWidth, title: a.title, visible: a.visible !== false },
    };
  });
}

/** The serial of the image annotation a create call added: the scene it returns, less `before`. */
export function newImageSerial(scene, before) {
  const listed = scene && Array.isArray(scene.annotations) ? scene.annotations : [];
  const added = listed.filter(x => x && Number.isInteger(x.serial) && !before.has(x.serial)
    && (x.type === undefined || String(x.type).toLowerCase() === 'image'));
  return added.length === 1 ? added[0].serial : null;
}

/** `token` null: requests carry no Authorization header (the local server of converted mode must
 * never see the Nanome token). */
function client(deps, token) {
  async function send(step, method, url, { json, form, auth = true, headers = {} } = {}) {
    const all = { ...headers };
    if (auth && token) all.Authorization = `Bearer ${token}`;
    let body;
    if (json !== undefined) {
      all['Content-Type'] = 'application/json';
      body = JSON.stringify(json);
    } else if (form !== undefined) {
      body = form; // fetch writes the multipart boundary itself
    }
    let res;
    try {
      res = await deps.fetch(url, { method, headers: all, body });
    } catch (e) {
      // no answer at all: the request was dropped (or the browser hid a gateway error without CORS headers)
      throw Object.assign(new ImportFailure(step, `${method} ${url} failed: ${(e && e.message) || e}`, { url }), { dropped: true });
    }
    if (!res.ok) {
      throw new ImportFailure(step, `${method} ${url} returned HTTP ${res.status}`, { status: res.status, body: await bodyText(res), url });
    }
    return res;
  }

  async function json(step, method, url, options) {
    const res = await send(step, method, url, options);
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch {
      throw new ImportFailure(step, `${method} ${url} did not return JSON`, { status: res.status, body: text, url });
    }
  }

  return { send, json };
}

/** v2's answer to a workspace creation that ran into another change to the same account's
 * workspaces (two imports at once, the web app creating one): HTTP 400 whose body names a database
 * operation "expected to affect 1 row(s)". Nothing was created, so the request can be sent again. */
export function isConcurrencyFailure(e) {
  return e instanceof ImportFailure && e.status === 400 && /expected to affect 1 row/.test(e.body);
}

/**
 * `attempt()`, called again after a concurrency failure (isConcurrencyFailure), up to `retries`
 * more times; any other failure, and the last concurrency failure, is thrown as it is (the last
 * with the number of tries added to its message). The pause before try n + 1 is n to n + 1 times
 * `seconds`, at random, so that two imports that ran into each other do not do so again.
 * onRetry(n, retries) is called before each pause.
 */
export async function retryConcurrency(attempt, { retries = DEFAULTS.workspaceRetries, seconds = DEFAULTS.workspaceRetrySeconds, sleep, onRetry = () => {} } = {}) {
  const pause = sleep || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const limit = Math.max(0, Math.floor(Number(retries) || 0));
  for (let n = 1; ; n++) {
    try {
      return await attempt();
    } catch (e) {
      if (!isConcurrencyFailure(e)) throw e;
      if (n > limit) {
        if (limit) e.message += `; v2 answered ${n} tries with this concurrency error`;
        throw e;
      }
      onRetry(n, limit);
      await pause(Math.max(0, Number(seconds) || 0) * 1000 * (n + Math.random()));
    }
  }
}

// --- the import ---------------------------------------------------------------------------------------

/**
 * Import one v1 session into a new v2 workspace.
 *
 * Tool-run mode (the default): bytes (ArrayBuffer | Uint8Array | Blob) and filename of the session;
 * MARA converts it. Converted mode: converted = {baseUrl, files, components, annotations,
 * imageAnnotations, summary, names, nothingToImport, scene} names outputs tool_main.py already
 * wrote (prepare_local.py); no MARA tool run.
 *
 * Both: token (a Nanome token MARA and the Workspace API accept), maraUrl, workspaceApiUrl
 * (default: MARA /api/info), workspaceName, entryNames, verify, verifyModels, verifyAtoms,
 * verifyDetail, tolerance, slowLoadSeconds, loadRecoverSeconds, loadRecoverMax, loadPollSeconds,
 * workspaceRetries, workspaceRetrySeconds, emptySessions ('refuse': a session with nothing v2 can
 * show fails at step 'empty' instead of becoming an empty workspace), onProgress({step, message,
 * index, total}), and fetch / FormData / Blob / now (milliseconds) / sleep(ms) to use instead of
 * the globals. Tool-run mode also: toolId, toolArgs, deleteToolRun.
 *
 * Resolves to {workspaceId, url, summary, notes, warnings, entries, verification, ...}; rejects with
 * an ImportFailure naming the step and carrying the server's response body. A failure after the
 * workspace was created leaves the workspace in place and names it in `partial`.
 */
export async function runImport(options = {}) {
  const o = { ...DEFAULTS, ...options, toolArgs: { ...DEFAULTS.toolArgs, ...(options.toolArgs || {}) } };
  const deps = {
    fetch: o.fetch || ((...args) => globalThis.fetch(...args)),
    FormData: o.FormData || globalThis.FormData,
    Blob: o.Blob || globalThis.Blob,
    now: o.now || (() => Date.now()),
    sleep: o.sleep || (ms => new Promise(resolve => setTimeout(resolve, ms))),
  };
  const ctx = { step: 'input', partial: {} };
  const progress = (step, message, extra = {}) => {
    if (typeof o.onProgress !== 'function') return;
    try {
      o.onProgress({ step, message, ...extra });
    } catch {
      // a broken progress display must not break the import
    }
  };
  try {
    return await importSession(o, deps, ctx, progress);
  } catch (error) {
    const failure = error instanceof ImportFailure ? error : new ImportFailure(ctx.step, (error && error.message) || String(error));
    failure.partial = { ...ctx.partial };
    if (ctx.partial.workspaceUrl) failure.message += ` (the workspace was created and left as it is: ${ctx.partial.workspaceUrl})`;
    throw failure;
  }
}

/** Tool-run mode: MARA converts the session; returns what the rest of the import needs. */
async function toolRunSource(o, deps, http, mara, ctx, progress) {
  const filename = String(o.filename || 'session.nanome').split(/[\\/]/).pop();
  const warnings = SESSION_EXTENSION.test(filename) ? [] : [`${filename} does not end in .nanome or .nanoscenes; converting it anyway.`];

  // The importer tool must be there and visible to this user.
  ctx.step = 'tool';
  progress('tool', `Checking MARA tool ${o.toolId}`);
  const tool = await http.json('tool', 'GET', `${mara}/api/tools/${encodeURIComponent(o.toolId)}`);
  const fileArg = ((tool && tool.args_list) || []).find(arg => arg && arg.name === 'input_file');
  if (!fileArg || fileArg.type !== 'file') {
    throw new ImportFailure('tool', `MARA tool ${o.toolId} (${tool && tool.name}) has no "input_file" file argument; is it the Nanome v1 Session Importer?`, {
      body: JSON.stringify(tool && tool.args_list),
    });
  }

  ctx.step = 'convert';
  const uploadName = uploadNameFor(filename);
  progress('convert', `Converting ${filename} with "${tool.name}" on MARA`);
  const run = await http.json('convert', 'POST', `${mara}/api/tools/${encodeURIComponent(o.toolId)}/run`, {
    form: toolRunForm(deps, { bytes: o.bytes, uploadName, args: o.toolArgs }),
  });
  if (!run || !run.run_id) throw new ImportFailure('convert', 'MARA returned no run_id', { body: JSON.stringify(run) });
  ctx.partial.toolRunId = run.run_id;
  const summary = typeof run.result === 'string' ? run.result : JSON.stringify(run.result);

  ctx.step = 'outputs';
  let outputs;
  try {
    outputs = parseToolOutputs(summary, run.filenames);
  } catch (e) {
    throw new ImportFailure('outputs', `${e.message}. MARA returned: ${JSON.stringify(run.filenames)}`, { body: summary });
  }
  const runFiles = `${mara}/api/tools/runs/${encodeURIComponent(run.run_id)}/`;
  return {
    mode: 'tool',
    filename,
    summary,
    outputs,
    warnings: [...warnings, ...outputs.warnings],
    fetchFile: file => http.send('download', 'GET', runFiles + encodeURIComponent(file)),
    toolRun: { id: run.run_id, toolId: o.toolId, files: run.filenames },
  };
}

/** Converted mode: the outputs are already on a server; nothing is sent there but GETs. */
function convertedSource(o, deps) {
  let outputs;
  try {
    outputs = convertedOutputs(o.converted);
  } catch (e) {
    throw new ImportFailure('input', e.message);
  }
  const local = client(deps, null);
  return {
    mode: 'converted',
    filename: o.filename || `${outputs.base || 'session'}.nanome`,
    summary: typeof o.converted.summary === 'string' ? o.converted.summary : '',
    outputs,
    warnings: [...outputs.warnings],
    fetchFile: file => local.send('download', 'GET', new URL(encodeURIComponent(file), outputs.baseUrl).href),
    toolRun: null,
  };
}

/** The serials v2 gave the components just added (`sent`, in add order) to the new workspace's
 * scene, which held none before. v2 numbers a component one past the scene's highest serial
 * but lists components in no set order, so sorted by serial they are the
 * ones sent, in order; their names must say so, or nothing is hidden. */
async function addedComponentSerials(http, componentsUrl, sent) {
  const listed = await http.json('components', 'GET', componentsUrl);
  const fail = message => new ImportFailure('components', message, { body: JSON.stringify(listed), url: componentsUrl });
  if (!Array.isArray(listed) || listed.length !== sent.length) {
    throw fail(`the scene lists ${Array.isArray(listed) ? listed.length : 'no'} component(s) after ${sent.length} were added to it, so the ones to hide cannot be told apart`);
  }
  if (listed.some(c => !c || !Number.isInteger(c.serial))) throw fail('the scene lists a component without a serial');
  const ordered = [...listed].sort((a, b) => a.serial - b.serial);
  const wrong = ordered.findIndex((c, i) => c.name !== sent[i].name);
  if (wrong >= 0) {
    throw fail(`the scene's components, in serial order, are not the ones added: #${wrong + 1} is "${ordered[wrong].name}" (serial ${ordered[wrong].serial}), "${sent[wrong].name}" was added`);
  }
  return ordered.map(c => c.serial);
}

/**
 * After a load request v2 dropped or answered 502/503/504: the entry v2 made of the file anyway,
 * read off the workspace (GET /workspaces/{id} lists its entries with their model ids, as
 * load-multiple answers them) every `pauseMs` for up to `limitMs`. An entry counts once two reads
 * in a row show it with the same models; one first seen on the last read gets one read more.
 * `known`: serials of the entries loaded before. Resolves to {entry, waited} (entry: serial, name,
 * models), or {entry: null, many, waited} when more than one new entry appeared (they cannot be
 * told apart), or {entry: null, waited, lastError} when none did (waited in ms). Reads that fail
 * are retried until the time is up (the API may be restarting).
 */
async function entryAfterFailedLoad(http, deps, { wsBase, known, limitMs, pauseMs, onWait = () => {} }) {
  const started = deps.now();
  let seen = null; // {serial, models} of the new entry on the read before
  let lastError = null;
  let extra = false;
  for (;;) {
    let workspace = null;
    try {
      workspace = await http.json('load', 'GET', wsBase);
      lastError = null;
    } catch (e) {
      lastError = e;
    }
    if (workspace) {
      const fresh = (workspace && Array.isArray(workspace.entries) ? workspace.entries : [])
        .filter(e => e && Number.isInteger(e.serial) && !known.has(e.serial));
      if (fresh.length > 1) return { entry: null, many: fresh, waited: deps.now() - started };
      const now = fresh.length ? { serial: fresh[0].serial, models: Array.isArray(fresh[0].models) ? fresh[0].models.length : null } : null;
      if (now && seen && now.serial === seen.serial && now.models === seen.models) return { entry: fresh[0], waited: deps.now() - started };
      seen = now;
    }
    const waited = deps.now() - started;
    if (waited >= limitMs) {
      if (!seen || extra) return { entry: null, waited, lastError };
      extra = true;
    }
    onWait(waited);
    await deps.sleep(pauseMs);
  }
}

/** A failed read of the workspace, for a message: its HTTP status, never the browser's own text
 * ("Failed to fetch" in a failure's message means the load request itself got no answer; only
 * that request may say so). */
const readFailure = e => (e && Number.isInteger(e.status) ? `HTTP ${e.status}` : 'no answer');

async function importSession(o, deps, ctx, progress) {
  const step = name => {
    ctx.step = name;
  };
  if (!o.token) throw new ImportFailure('input', 'no Nanome token');
  const mara = trimSlash(o.maraUrl);
  const http = client(deps, o.token);
  const converted = o.converted !== undefined && o.converted !== null;
  // Inputs first, before any request.
  const given = converted ? convertedSource(o, deps) : null;
  if (!converted && !byteSize(o.bytes)) throw new ImportFailure('input', 'the session file is empty or missing');

  // 1. MARA's settings name the Workspace API.
  let ws = trimSlash(o.workspaceApiUrl || '');
  if (!ws || !converted) {
    step('info');
    progress('info', `Reading ${mara}/api/info`);
    const info = await http.json('info', 'GET', `${mara}/api/info`, { auth: false });
    ws = ws || trimSlash((info && info.workspace_api_url) || '');
    if (!ws) throw new ImportFailure('info', `${mara}/api/info names no workspace_api_url`, { body: JSON.stringify(info) });
    if (!converted && info && info.enable_python_tools === false) {
      throw new ImportFailure('info', `${mara} has Python tools turned off (enable_python_tools is false), so the importer tool cannot run`);
    }
  }

  // 2. The converted files: from a MARA tool run, or given.
  const source = given || (await toolRunSource(o, deps, http, mara, ctx, progress));
  const { outputs, summary, filename } = source;
  const warnings = [...source.warnings];
  step('outputs');
  const structures = outputs.structures;
  // nothing v2 can show: the workspace is still made (empty, as v1 opens the session), with the
  // tool's own words on why, unless the caller refuses such sessions
  const empty = !structures.length && !outputs.imageAnnotationsFile;
  if (empty) {
    const said = /^Nothing to import: .*$/m.exec(String(summary || ''));
    const text = said ? said[0] : 'The v1 session holds no structure and no image or PDF page v2 can show; the workspace is empty, as v1 opens it.';
    if (o.emptySessions === 'refuse') throw Object.assign(new ImportFailure('empty', text, { body: summary }), { nothingToImport: true });
    warnings.push(text);
  }
  if (structures.length > o.freeEntryLimit) {
    warnings.push(`This session has ${structures.length} structures; a free Nanome license holds at most ${o.freeEntryLimit} per workspace, so the load fails on a free license.`);
  }
  progress('outputs', `${structures.length} structure file(s), ${[outputs.componentsFile, outputs.annotationsFile, outputs.imageAnnotationsFile].filter(Boolean).join(', ')}`);

  // 3. Download them.
  step('download');
  const wanted = [...structures.map(s => s.file), outputs.componentsFile, outputs.annotationsFile, outputs.imageAnnotationsFile].filter(Boolean);
  const bytesOf = new Map();
  for (const [i, file] of wanted.entries()) {
    progress('download', `Downloading ${file}`, { index: i + 1, total: wanted.length });
    const res = await source.fetchFile(file);
    bytesOf.set(file, new Uint8Array(await res.arrayBuffer()));
  }
  const textOf = file => new TextDecoder().decode(bytesOf.get(file));
  const readJson = file => {
    try {
      return JSON.parse(textOf(file));
    } catch (e) {
      throw new ImportFailure('download', `${file} is not JSON: ${e.message}`, { body: textOf(file) });
    }
  };
  const components = readJson(outputs.componentsFile);
  const annotations = outputs.annotationsFile ? readJson(outputs.annotationsFile) : [];
  let images = [];
  if (outputs.imageAnnotationsFile) {
    const list = readJson(outputs.imageAnnotationsFile);
    try {
      images = imageAnnotationRequests(list, new Map(structures.map(s => [s.index, s.index])));
    } catch (e) {
      throw new ImportFailure('check', `${outputs.imageAnnotationsFile}: ${e.message}`, { body: textOf(outputs.imageAnnotationsFile) });
    }
    const files = [...new Set(images.map(a => a.file))];
    for (const [i, file] of files.entries()) {
      progress('download', `Downloading image ${file}`, { index: i + 1, total: files.length });
      const res = await source.fetchFile(file);
      bytesOf.set(file, new Uint8Array(await res.arrayBuffer()));
    }
  }
  // Check the files before anything is created: remap against 1..N, the tool's own numbering.
  step('check');
  const identity = new Map(structures.map(s => [s.index, s.index]));
  remapComponents(components, identity);
  annotationMutations(remapAnnotations(annotations, identity), new Map(structures.map(s => [s.index, 1])));

  // 4. A new, empty workspace (it comes with one scene).
  step('workspace');
  const workspaceName = o.workspaceName || workspaceNameFor(filename);
  progress('workspace', `Creating workspace "${workspaceName}"`);
  const description = (source.toolRun
    ? `Converted from the Nanome v1 session ${filename} (MARA tool run ${source.toolRun.id}).`
    : `Converted from the Nanome v1 session ${filename} by a local converter (${outputs.baseUrl}).`)
    + (outputs.description ? ` ${outputs.description}` : '');
  let workspaceRetries = 0;
  const workspace = await retryConcurrency(() => http.json('workspace', 'POST', `${ws}/workspaces`, { json: { name: workspaceName, description } }), {
    retries: o.workspaceRetries, seconds: o.workspaceRetrySeconds, sleep: deps.sleep,
    onRetry: (n, limit) => {
      workspaceRetries = n;
      progress('workspace', `Nanome 2 was changing this account's workspaces and created none; asking again (${n} of ${limit})`);
    },
  });
  if (!workspace || !workspace.id) throw new ImportFailure('workspace', 'the Workspace API returned no workspace id', { body: JSON.stringify(workspace) });
  const url = `${mara}/workspaces/${encodeURIComponent(workspace.id)}`;
  ctx.partial.workspaceId = workspace.id;
  ctx.partial.workspaceUrl = url;
  const wsBase = `${ws}/workspaces/${encodeURIComponent(workspace.id)}`;

  // 5. Load the structures in the tool's order, one file per request. v2 loads the files of one
  // request one after another, so one request holding every file of
  // a large session can outlast the gateway's timeout (HTTP 504 after about 5 minutes).
  step('load');
  const uploads = structures.map(s => ({ ...s, uploadName: o.entryNames === 'file' ? s.file : entryUploadName(s.name, s.format, s.file) }));
  // Entry serials only grow and are never reused, so take them from the answers, not 1..N.
  const serials = new Map();
  const entries = [];
  // waiting for the entries of failed loads: one budget for the whole import, so a session of
  // many huge files cannot wait loadRecoverSeconds for each
  const recovery = {
    totalMs: Math.max(0, Number(o.loadRecoverSeconds) || 0) * 1000, spentMs: 0,
    max: Math.max(0, Math.floor(Number(o.loadRecoverMax) || 0)), loads: 0,
    pauseMs: Math.max(1, Number(o.loadPollSeconds) || 0) * 1000,
  };
  for (const [i, u] of uploads.entries()) {
    progress('load', `Loading structure file ${i + 1}/${uploads.length}: ${u.uploadName}`, { index: i + 1, total: uploads.length });
    const where = `structure file ${i + 1} of ${uploads.length}, ${u.file}; ${i} of the ${uploads.length} were loaded before it`;
    const started = deps.now();
    let loaded;
    try {
      loaded = await http.json('load', 'POST', `${wsBase}/entries/load-multiple`, {
        form: loadForm(deps, [{ name: u.uploadName, bytes: bytesOf.get(u.file) }]),
      });
    } catch (e) {
      if (!(e instanceof ImportFailure)) throw e;
      e.message += ` (${where})`;
      // v2 may still be loading the file (a huge one outlasts the gateway): wait for its entry.
      // A plain 500 is v2's own error (nothing was committed): it fails at once, as do 4xx.
      if (!(e.dropped || [502, 503, 504].includes(e.status)) || !(recovery.totalMs > 0 && recovery.max > 0)) throw e;
      if (recovery.loads >= recovery.max || recovery.spentMs >= recovery.totalMs) {
        e.message += `; not waited for: this import already waited ${Math.round(recovery.spentMs / 1000)} s for the entries of ${recovery.loads} failed load(s)`
          + ` (at most ${recovery.max} load(s) and ${Math.round(recovery.totalMs / 1000)} s per import)`;
        throw e;
      }
      recovery.loads++;
      const answer = e.dropped ? `v2 dropped the request (${(/ failed: (.*?) \(structure file /.exec(e.message) || [])[1] || 'no answer'})` : `v2 answered HTTP ${e.status}`;
      const limitMs = recovery.totalMs - recovery.spentMs;
      const found = await entryAfterFailedLoad(http, deps, {
        wsBase, known: new Set(serials.values()), limitMs, pauseMs: recovery.pauseMs,
        onWait: waited => progress('load', `${answer} loading ${u.uploadName}; waiting for its entry in the workspace (${Math.round(waited / 1000)} s of ${Math.round(limitMs / 1000)} s)`,
          { index: i + 1, total: uploads.length }),
      });
      recovery.spentMs += found.waited;
      if (!found.entry) {
        e.message += found.many
          ? `; then ${found.many.length} new entries appeared in the workspace (${found.many.map(x => x.serial).join(', ')}), which cannot be matched to the file`
          : `; no entry for it appeared in the workspace within ${Math.round(found.waited / 1000)} s` +
            (found.lastError ? `, and the last read of the workspace failed (${readFailure(found.lastError)})` : '');
        throw e;
      }
      loaded = [found.entry];
      warnings.push(`${answer} loading ${u.file}, but v2 went on loading it: entry ${found.entry.serial} was in the workspace ${Math.round((deps.now() - started) / 1000)} s after the request was sent.`);
    }
    const seconds = Math.max(0, deps.now() - started) / 1000;
    if (!Array.isArray(loaded) || loaded.length !== 1) {
      throw new ImportFailure('load', `the Workspace API created ${Array.isArray(loaded) ? loaded.length : 'no'} entries for one structure file, so they cannot be matched to it (${where})`, {
        body: JSON.stringify(loaded),
      });
    }
    const entry = loaded[0];
    if (!entry || !Number.isInteger(entry.serial)) throw new ImportFailure('load', `the entry came back without a serial (${where})`, { body: JSON.stringify(entry) });
    if ([...serials.values()].includes(entry.serial)) throw new ImportFailure('load', `entry serial ${entry.serial} came back a second time (${where})`, { body: JSON.stringify(entry) });
    serials.set(u.index, entry.serial);
    entries.push({
      serial: entry.serial,
      name: entry.name,
      file: u.file,
      format: u.format,
      models: Array.isArray(entry.models) ? entry.models.length : null,
      openFrame: u.openFrame || null,
      loadSeconds: Math.round(seconds * 10) / 10,
    });
    ctx.partial.entries = entries.map(({ serial, name, file, loadSeconds }) => ({ serial, name, file, loadSeconds }));
    if (seconds > o.slowLoadSeconds) warnings.push(`v2 took ${Math.round(seconds)} s to load ${u.file}.`);
    const sent = u.uploadName.replace(/\.[^.]*$/, '');
    if (entry.name !== sent) warnings.push(`Entry ${entry.serial} came back named "${entry.name}"; it was sent as "${sent}".`);
  }

  // 6. The scene the components go into.
  step('scene');
  const scenes = await http.json('scene', 'GET', `${wsBase}/scenes`);
  const scene = Array.isArray(scenes) && scenes.length ? scenes.reduce((a, b) => (b.serial < a.serial ? b : a)) : null;
  if (!scene || !Number.isInteger(scene.serial) || !scene.id) throw new ImportFailure('scene', 'the new workspace has no scene', { body: JSON.stringify(scenes) });

  // 7. Components, one POST each, the same body MARA's Add Components tool sends, except that the
  // components of structures hidden in v1 go with their visualizations on and are then hidden
  // with one toggle-hidden call (componentsToSend).
  step('components');
  const { send: toAdd, hideIndexes } = componentsToSend(remapComponents(components, serials).map(restComponent));
  const componentsUrl = `${wsBase}/scenes/${scene.serial}/components`;
  for (const [i, component] of toAdd.entries()) {
    progress('components', `Adding component ${i + 1}/${toAdd.length}: ${component.name}`, { index: i + 1, total: toAdd.length });
    try {
      await http.json('components', 'POST', `${componentsUrl}/add`, { json: component });
    } catch (e) {
      if (e instanceof ImportFailure) e.message += ` (component ${i + 1} of ${toAdd.length}, "${component.name}"; the ${i} before it were added)`;
      throw e;
    }
  }
  let hiddenSerials = [];
  if (hideIndexes.length) {
    progress('components', `Hiding ${hideIndexes.length} component(s) of structures hidden in v1`);
    try {
      const added = await addedComponentSerials(http, componentsUrl, toAdd);
      hiddenSerials = hideIndexes.map(i => added[i]);
      await http.json('components', 'POST', `${componentsUrl}/toggle-hidden`, { json: { componentSerials: hiddenSerials, hidden: true } });
    } catch (e) {
      if (e instanceof ImportFailure) e.message += ` (all ${toAdd.length} components were added; the ${hideIndexes.length} to hide are not hidden and show their representations)`;
      throw e;
    }
  }

  // 8. The frame each entry opens on. v2 opens every entry on its first model;
  // where v1 opens a structure on another frame (a Vault upload or
  // scene deck on its last, a conformer set on the one saved), the scene is set to that model.
  // The files number their models 1..N in v1's frame order (PDB MODEL, mmCIF
  // pdbx_PDB_model_num, SDF records), which is how v2 numbers them.
  step('frames');
  const openedOn = new Map(); // entry serial -> model serial set
  for (const entry of entries) {
    if (!entry.openFrame || entry.openFrame === 1) continue;
    if (entry.models !== null && entry.openFrame > entry.models) {
      warnings.push(`Entry ${entry.serial} (${entry.name}): v1 opens it on frame ${entry.openFrame}, but v2 made ${entry.models} model(s); left on the first.`);
      continue;
    }
    progress('frames', `Opening ${entry.name} on frame ${entry.openFrame}, as v1 does`);
    try {
      await http.json('frames', 'POST', `${wsBase}/scenes/${scene.serial}/entries/${entry.serial}/model-serial`, { json: { modelSerial: entry.openFrame } });
    } catch (e) {
      if (e instanceof ImportFailure) e.message += ` (entry ${entry.serial}, ${entry.name}, frame ${entry.openFrame})`;
      throw e;
    }
    openedOn.set(entry.serial, entry.openFrame);
  }

  // 9. Annotations through GraphQL, one mutation per type.
  step('annotations');
  let annotationCount = 0;
  if (annotations.length) {
    const currentModels = new Map((scene.entryModelSerial || []).map(m => [m.entrySerial, m.modelSerial]));
    const groups = annotationMutations(remapAnnotations(annotations, serials), currentModels);
    for (const { mutation, inputs } of groups) {
      progress('annotations', `Adding ${inputs.length} annotation(s) with ${mutation}`);
      const body = await http.json('annotations', 'POST', `${ws}/graphql`, {
        json: { query: annotationMutationQuery(mutation), variables: { input: { sceneId: scene.id, annotations: inputs } } },
        headers: { Accept: 'application/json' },
      });
      const errors = graphqlErrors(body, mutation);
      if (errors.length) {
        const before = annotationCount ? ` (${annotationCount} annotation(s) of other types were added before)` : '';
        throw new ImportFailure('annotations', `${mutation} failed: ${errors.join('; ')}${before}`, { body: JSON.stringify(body) });
      }
      annotationCount += inputs.length;
    }
  }

  // 9b. v1's images and PDF pages as image annotations: create each, then upload its picture. A
  // picture that does not go up is removed again and reported; the workspace stays.
  step('images');
  let imageCount = 0;
  const imageProblems = [];
  const placed = [];   // scene-anchored images that went up: where they are, to face them
  if (images.length) {
    const annotationsUrl = `${wsBase}/scenes/${scene.serial}/annotations`;
    const listed = await http.json('images', 'GET', annotationsUrl);
    let before = new Set((Array.isArray(listed) ? listed : []).map(x => x && x.serial));
    const requests = imageAnnotationRequests(JSON.parse(textOf(outputs.imageAnnotationsFile)), serials);
    for (const [i, a] of requests.entries()) {
      progress('images', `Adding image ${i + 1}/${requests.length}: ${a.body.title}`, { index: i + 1, total: requests.length });
      let serial = null;
      try {
        const sceneNow = await http.json('images', 'POST', `${annotationsUrl}/image`, { json: a.body });
        serial = newImageSerial(sceneNow, before);
        if (serial === null) throw new ImportFailure('images', 'the new image annotation is not in the scene the API returned', { body: JSON.stringify(sceneNow).slice(0, 2000) });
        before = new Set((sceneNow.annotations || []).map(x => x && x.serial));
        const form = new deps.FormData();
        form.append('file', new deps.Blob([bytesOf.get(a.file)], { type: a.mime }), a.file);
        await http.send('images', 'PUT', `${annotationsUrl}/${serial}/image`, { form });
        imageCount++;
        if (a.body.anchor.eAnchorType === 'Scene' && a.body.anchor.offset) {
          placed.push({ offset: a.body.anchor.offset, width: a.body.targetWidth, visible: a.body.visible });
        }
      } catch (e) {
        imageProblems.push(`image ${i + 1} "${a.body.title}" (${a.file}): ${e.message}`);
        if (serial !== null) {
          try {
            await http.send('images', 'DELETE', `${annotationsUrl}/${serial}`);
            before.delete(serial);
          } catch (e2) {
            imageProblems.push(`  and its empty annotation ${serial} could not be removed: ${e2.message}`);
          }
        }
      }
    }
    if (imageProblems.length) warnings.push(...imageProblems.map(p => `Image annotations: ${p}`));
  }

  // v2 fits its view to the structures it loads; with images only it does not, and they sit out of
  // sight (the converter writes them in v1's workspace frame). Turn the scene to face them, the
  // shown ones first: rotation (0, sqrt 1/2, sqrt 1/2, 0) undoes v2's y/z swap and v1's x mirror,
  // keeping v1's up as up.
  let pointOfView = null;
  if (!entries.length && placed.length) {
    step('view');
    progress('view', 'Turning the scene to face the images');
    const pts = placed.some(p => p.visible) ? placed.filter(p => p.visible) : placed;
    const SCALE = 0.02;
    const c = ['x', 'y', 'z'].map(k => pts.reduce((sum, p) => sum + p.offset[k], 0) / pts.length);
    const r = Math.max(...pts.map(p => SCALE * (Math.hypot(p.offset.x - c[0], p.offset.y - c[1], p.offset.z - c[2]) + p.width / 2)));
    const d = Math.max(0.4, r / (Math.tan(Math.PI / 6) * 0.8));
    const transform = { position: { x: SCALE * c[0], y: -SCALE * c[1], z: d - 0.5 - SCALE * c[2] },
      rotation: { x: 0, y: Math.SQRT1_2, z: Math.SQRT1_2, w: 0 }, scale: SCALE };
    try {
      const b = await http.json('view', 'POST', `${ws}/graphql`, {
        json: { query: 'mutation($input: SetScenePointOfViewInput!) { setScenePointOfView(input: $input) { __typename } }', variables: { input: { sceneId: scene.id, transform } } },
        headers: { Accept: 'application/json' },
      });
      if (b && b.errors) warnings.push(`Could not turn the scene to face the images: ${JSON.stringify(b.errors).slice(0, 300)}`);
      else pointOfView = transform;
    } catch (e) {
      warnings.push(`Could not turn the scene to face the images: ${e.message}`);
    }
  }

  // 10. Read back what v2 stored.
  let verification = { ok: null, skipped: true, text: 'Not verified.', entries: [], problems: [], notes: [] };
  if (o.verify !== false) {
    step('verify');
    verification = await verifyImport(http, { wsBase, scene, entries, textOf, componentCount: toAdd.length, hiddenSerials, annotationCount: annotationCount + imageCount, o, progress });
    warnings.push(...verification.problems.map(p => `Verification: ${p}`));
  }

  // 11. Optionally drop MARA's copy of the upload and outputs.
  if (o.deleteToolRun && source.toolRun) {
    step('cleanup');
    try {
      await http.send('cleanup', 'DELETE', `${mara}/api/tools/runs/${encodeURIComponent(source.toolRun.id)}`);
      source.toolRun.deleted = true;
    } catch (e) {
      warnings.push(`Could not delete MARA tool run ${source.toolRun.id}: ${e.message}`);
    }
  }

  progress('done', `Workspace ready: ${url}`);
  return {
    mode: source.mode,
    workspaceId: workspace.id,
    url,
    workspaceName,
    workspaceRetries,
    sceneSerial: scene.serial,
    summary,
    notes: summaryNotes(summary),
    warnings,
    entries: entries.map(({ serial, name, file, format, openFrame, loadSeconds }) => ({ serial, name, file, format, openFrame, loadSeconds })),
    components: toAdd.length,
    hiddenComponents: hiddenSerials.length,
    annotations: annotationCount,
    images: imageCount,
    imageProblems,
    empty,
    nothingToImport: outputs.nothingToImport || null,
    scene: outputs.scene || null,
    pointOfView,
    verification,
    toolRun: source.toolRun ? { deleted: false, ...source.toolRun } : null,
    converted: source.mode === 'converted' ? { baseUrl: outputs.baseUrl, files: structures.map(s => s.file), components: outputs.componentsFile, annotations: outputs.annotationsFile, imageAnnotations: outputs.imageAnnotationsFile,
      nothingToImport: outputs.nothingToImport || null, scene: outputs.scene || null } : null,
  };
}

async function verifyImport(http, { wsBase, scene, entries, textOf, componentCount, hiddenSerials = [], annotationCount, o, progress }) {
  const report = {
    ok: true, skipped: false, detail: o.verifyDetail, tolerance: o.tolerance, entries: [], problems: [], notes: [],
    models: 0, atoms: 0, maxDeviation: 0, elementMismatches: 0, chargeMismatches: 0, bondMismatches: 0,
    metadataItems: 0, metadataMismatches: 0, text: '',
  };
  for (const [i, entry] of entries.entries()) {
    progress('verify', `Checking entry ${entry.serial} (${entry.name}) against ${entry.file}`, { index: i + 1, total: entries.length });
    const result = { serial: entry.serial, name: entry.name, file: entry.file, format: entry.format, fileModels: null, v2Models: entry.models, models: [], problems: [], notes: [] };
    report.entries.push(result);
    let expected;
    try {
      expected = parseStructure(textOf(entry.file), entry.format);
    } catch (e) {
      result.problems.push(`could not read ${entry.file}: ${e.message}`);
      continue;
    }
    result.fileModels = expected.length;
    if (entry.models !== null && entry.models !== expected.length) {
      result.problems.push(`${entry.models} model(s) in v2, ${expected.length} in the file`);
    }
    for (const k of sampleIndices(expected.length, o.verifyModels)) {
      const model = expected[k];
      let stored;
      try {
        stored = await http.json('verify', 'GET', `${wsBase}/entries/${entry.serial}/models/${model.serial}`);
      } catch (e) {
        result.problems.push(`model ${model.serial}: ${e.message}${e.body ? ` ${e.body.slice(0, 300)}` : ''}`);
        continue;
      }
      const check = compareModel(model, stored, { samples: o.verifyAtoms, tolerance: o.tolerance, format: entry.format, full: o.verifyDetail === 'full' });
      result.models.push(check);
      result.problems.push(...check.problems.map(p => `model ${model.serial}: ${p}`));
      result.notes.push(...check.notes.map(p => `model ${model.serial}: ${p}`));
      report.models += 1;
      report.atoms += check.checked;
      report.maxDeviation = Math.max(report.maxDeviation, check.maxDeviation);
      report.elementMismatches += check.elements.mismatches;
      report.chargeMismatches += check.charges.mismatches;
      report.bondMismatches += check.bonds.missing + check.bonds.kindMismatches + (check.bonds.extra || 0);
      report.metadataItems += check.metadata.items;
      report.metadataMismatches += check.metadata.missing.length + check.metadata.differ.length + check.metadata.extra.length;
    }
  }
  for (const result of report.entries) {
    report.problems.push(...result.problems.map(p => `entry ${result.serial} (${result.file}): ${p}`));
    report.notes.push(...result.notes.map(p => `entry ${result.serial} (${result.file}): ${p}`));
  }

  // The scene should hold exactly what was added: v2 adds no components when it loads PDB, mmCIF or
  // SDF (it adds only what the loader returns, and these loaders return none).
  const list = async (what, path, expected) => {
    try {
      const listed = await http.json('verify', 'GET', `${wsBase}/scenes/${scene.serial}/${path}`);
      const found = Array.isArray(listed) ? listed.length : NaN;
      if (found !== expected) report.problems.push(`the scene has ${found} ${what}; ${expected} were added`);
      return { found, listed: Array.isArray(listed) ? listed : null };
    } catch (e) {
      report.problems.push(`could not list the scene's ${what}: ${e.message}`);
      return { found: null, listed: null };
    }
  };
  const sceneComponents = await list('components', 'components', componentCount);
  report.sceneComponents = sceneComponents.found;
  report.sceneAnnotations = (await list('annotations', 'annotations', annotationCount)).found;

  // Exactly the components the import hid are hidden.
  report.hiddenComponents = hiddenSerials.length;
  report.sceneHiddenComponents = null;
  if (sceneComponents.listed) {
    const listed = sceneComponents.listed.filter(c => c && typeof c === 'object');
    const bySerial = new Map(listed.map(c => [c.serial, c]));
    const meant = new Set(hiddenSerials);
    const hidden = listed.filter(c => c.hidden === true);
    const noFlag = listed.filter(c => typeof c.hidden !== 'boolean');
    const shown = hiddenSerials.filter(serial => !bySerial.has(serial) || bySerial.get(serial).hidden !== true);
    const unmeant = hidden.filter(c => !meant.has(c.serial));
    const named = serial => (bySerial.has(serial) ? `${serial} "${bySerial.get(serial).name}"` : `${serial} (not in the scene)`);
    report.sceneHiddenComponents = hidden.length;
    if (noFlag.length) report.problems.push(`the scene lists ${noFlag.length} component(s) without a hidden flag`);
    if (shown.length) report.problems.push(`${shown.length} component(s) the import hid (every representation off in v1) are not hidden in the scene: ${listing(shown.map(named))}`);
    if (unmeant.length) report.problems.push(`${unmeant.length} component(s) are hidden that the import did not hide: ${listing(unmeant.map(c => named(c.serial)))}`);
  }

  // Each entry shows the frame v1 opens it on (step 8), the first where v1 does too.
  report.framesSet = entries.filter(e => e.openFrame && e.openFrame > 1).length;
  try {
    const scenes = await http.json('verify', 'GET', `${wsBase}/scenes`);
    const now = (Array.isArray(scenes) ? scenes : []).find(s => s && s.serial === scene.serial);
    const shown = new Map(((now && now.entryModelSerial) || []).map(m => [m.entrySerial, m.modelSerial]));
    const wrong = entries.filter(e => shown.get(e.serial) !== (e.openFrame || 1));
    if (wrong.length) {
      report.problems.push(`${wrong.length} entr${wrong.length === 1 ? 'y shows' : 'ies show'} another frame than v1 opens on: ${listing(wrong.map(e => `${e.serial} "${e.name}" on ${shown.get(e.serial)}, v1 on ${e.openFrame || 1}`))}`);
    }
  } catch (e) {
    report.problems.push(`could not read the scene's current models: ${e.message}`);
  }

  report.ok = report.problems.length === 0;
  const counts = `${report.models} model(s), ${report.atoms} atom(s), largest coordinate deviation ${report.maxDeviation.toFixed(4)} A`;
  const hiddenText = hiddenSerials.length ? ` (${hiddenSerials.length} hidden, as in v1)` : '';
  report.text = report.ok && !entries.length
    ? `Verified the scene: no entries, ${componentCount} component(s) and ${annotationCount} annotation(s).`
    : report.ok
    ? `Verified ${entries.length} entr${entries.length === 1 ? 'y' : 'ies'}: ${counts}; elements, charges and bonds as in the files${report.metadataItems ? `, ${report.metadataItems} SD data item(s) kept as v2 model metadata` : ''}; ${componentCount} component(s)${hiddenText} and ${annotationCount} annotation(s) in the scene` +
      (report.framesSet ? `; ${report.framesSet} entr${report.framesSet === 1 ? 'y opens' : 'ies open'} on the frame v1 opens ${report.framesSet === 1 ? 'it' : 'them'} on` : '') + '.' +
      (report.notes.length ? ` ${report.notes.length} note(s) on differences v2 makes by design.` : '')
    : `Verification found ${report.problems.length} problem(s) (${counts}).`;
  return report;
}
