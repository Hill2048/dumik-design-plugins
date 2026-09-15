#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const LOADER_NAME = 'dumik-project-context.cjs';
const STATUS_MESSAGE = 'Loading DUMIK project context';
const MATCHER = 'startup|resume|clear|compact';
const source = path.resolve(__dirname, '../../../hooks/load-project-context.js');
const { isWithin } = require(source);

// Codex reads <project>/.codex/hooks.json; ZCode reads <project>/.zcode/config.json
// and only runs workspace hooks when hooks.enabled is true.
const HOSTS = {
  codex: {
    label: '.codex/hooks.json',
    config: (root) => path.join(root, '.codex', 'hooks.json'),
    loader: (root) => path.join(root, '.codex', 'hooks', LOADER_NAME),
  },
  zcode: {
    label: '.zcode/config.json',
    config: (root) => path.join(root, '.zcode', 'config.json'),
    loader: (root) => path.join(root, '.zcode', 'hooks', LOADER_NAME),
  },
};

function quotePosix(value) {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function quotePowerShell(value) {
  return `'${value.replace(/'/g, "''")}'`;
}

function assertLocalPath(root, filePath) {
  let current = filePath;
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) throw new Error(`Cannot resolve path: ${filePath}`);
    current = parent;
  }
  if (!isWithin(root, fs.realpathSync(current))) {
    throw new Error(`Refusing a path outside the selected project: ${filePath}`);
  }
  if (fs.existsSync(filePath) && fs.lstatSync(filePath).isSymbolicLink()) {
    throw new Error(`Refusing to overwrite a linked path: ${filePath}`);
  }
}

function resolveHost(requested = 'auto') {
  if (requested === 'codex' || requested === 'zcode') return requested;
  if (requested !== 'auto') {
    throw new Error('--host must be one of: auto, codex, zcode.');
  }
  return Object.keys(process.env).some((name) => name.startsWith('ZCODE_')) ? 'zcode' : 'codex';
}

function codexHandler(loaderPath) {
  const portablePath = loaderPath.replace(/\\/g, '/');
  return {
    type: 'command',
    command: `node ${quotePosix(portablePath)}`,
    commandWindows: `node ${quotePowerShell(portablePath)}`,
    timeout: 3,
    additionalContextLimit: 8000,
    statusMessage: STATUS_MESSAGE,
  };
}

function zcodeHandler(loaderPath) {
  return {
    type: 'process',
    command: 'node',
    args: [loaderPath.replace(/\\/g, '/')],
    timeoutMs: 5000,
    statusMessage: STATUS_MESSAGE,
  };
}

function isManagedHandler(item) {
  if (item.statusMessage === STATUS_MESSAGE) return true;
  if (typeof item.command === 'string' && item.command.includes(LOADER_NAME)) return true;
  return Array.isArray(item.args) &&
    item.args.some((arg) => typeof arg === 'string' && arg.includes(LOADER_NAME));
}

function assertGroups(groups) {
  if (!Array.isArray(groups) || groups.some((group) =>
    !group || typeof group !== 'object' || !Array.isArray(group.hooks))) {
    throw new Error('Existing SessionStart configuration was not changed.');
  }
}

// Registers the loader once. A differing or duplicated DUMIK entry is reported, not replaced.
function planGroups(groups, handler) {
  const managed = groups.filter((group) => group.hooks.some((item) => item && isManagedHandler(item)));
  if (!managed.length) {
    return { groups: [...groups, { matcher: MATCHER, hooks: [handler] }], changed: true };
  }
  const existing = managed[0];
  if (managed.length !== 1 || existing.matcher !== MATCHER ||
      existing.hooks.length !== 1 ||
      JSON.stringify(existing.hooks[0]) !== JSON.stringify(handler)) {
    throw new Error('An existing DUMIK context hook differs; it was not overwritten or duplicated.');
  }
  return { groups, changed: false };
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function planCodex(config, handler) {
  if (config.hooks !== undefined && !isPlainObject(config.hooks)) {
    throw new Error('Existing hooks.json has an unsupported structure; it was not changed.');
  }
  config.hooks ??= {};
  const groups = config.hooks.SessionStart ?? [];
  assertGroups(groups);
  const plan = planGroups(groups, handler);
  if (plan.changed) config.hooks.SessionStart = plan.groups;
  return plan.changed;
}

function planZCode(config, handler) {
  if (config.hooks !== undefined && !isPlainObject(config.hooks)) {
    throw new Error('Existing .zcode/config.json has an unsupported structure; it was not changed.');
  }
  const hooks = config.hooks ?? {};
  if (hooks.enabled === false) {
    throw new Error('Runtime hooks are disabled in .zcode/config.json (hooks.enabled: false); enable them or register the hook manually.');
  }
  if (hooks.events !== undefined && !isPlainObject(hooks.events)) {
    throw new Error('Existing hooks.events configuration was not changed.');
  }
  const events = hooks.events ?? {};
  const groups = events.SessionStart ?? [];
  assertGroups(groups);
  const plan = planGroups(groups, handler);
  if (plan.changed) events.SessionStart = plan.groups;
  const enabledChanged = hooks.enabled !== true;
  hooks.enabled = true;
  hooks.events = events;
  config.hooks = hooks;
  return plan.changed || enabledChanged;
}

function install(rootPath, options = {}) {
  const host = resolveHost(options.host);
  if (typeof rootPath !== 'string' || !path.isAbsolute(rootPath)) {
    throw new Error('--project-root must be an absolute directory path.');
  }
  const root = fs.realpathSync(rootPath);
  if (!fs.statSync(root).isDirectory()) throw new Error('Project root must be a directory.');
  for (const filename of ['AGENTS.md', 'design.md']) {
    const input = path.join(root, filename);
    if (!fs.existsSync(input) || !fs.statSync(input).isFile() ||
        !isWithin(root, fs.realpathSync(input))) {
      throw new Error(`Create or verify ${filename} in the selected project first.`);
    }
  }

  const configPath = HOSTS[host].config(root);
  const loaderPath = HOSTS[host].loader(root);
  assertLocalPath(root, configPath);
  assertLocalPath(root, loaderPath);

  const before = fs.existsSync(configPath) ? fs.readFileSync(configPath, 'utf8') : null;
  let config = {};
  if (before !== null) {
    try {
      config = JSON.parse(before.replace(/^\uFEFF/, ''));
    } catch {
      throw new Error(`Existing ${HOSTS[host].label} is not valid JSON; it was not changed.`);
    }
    if (!isPlainObject(config)) {
      throw new Error(`Existing ${HOSTS[host].label} has an unsupported structure; it was not changed.`);
    }
  }
  const configChanged = host === 'codex'
    ? planCodex(config, codexHandler(loaderPath))
    : planZCode(config, zcodeHandler(loaderPath));

  const loaderText = fs.readFileSync(source, 'utf8');
  if (fs.existsSync(loaderPath) && fs.readFileSync(loaderPath, 'utf8') !== loaderText) {
    throw new Error(`Existing ${LOADER_NAME} differs; preserve it and resolve the change explicitly.`);
  }

  fs.mkdirSync(path.dirname(loaderPath), { recursive: true });
  assertLocalPath(root, configPath);
  assertLocalPath(root, loaderPath);
  const current = fs.existsSync(configPath) ? fs.readFileSync(configPath, 'utf8') : null;
  if (current !== before) {
    throw new Error(`${HOSTS[host].label} changed during installation; retry after reviewing it.`);
  }
  let loaderChanged = false;
  if (!fs.existsSync(loaderPath)) {
    fs.writeFileSync(loaderPath, loaderText, { flag: 'wx' });
    loaderChanged = true;
  }
  if (configChanged) {
    fs.writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`, {
      flag: before === null ? 'wx' : 'w',
    });
  }
  return {
    status: configChanged || loaderChanged ? 'installed' : 'unchanged',
    projectRoot: root,
    host,
    hookConfig: configPath,
    loader: loaderPath,
    activation: 'requires-hook-trust',
  };
}

function main(argv) {
  if (argv.length === 1 && ['--help', '-h'].includes(argv[0])) {
    console.log('Usage: node install-project-context-hook.js --project-root <absolute-project-directory> [--host auto|codex|zcode]');
    return;
  }
  let projectRoot;
  let host = 'auto';
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index + 1];
    if (argv[index] === '--project-root' && value !== undefined) {
      projectRoot = value;
      index += 1;
    } else if (argv[index] === '--host' && value !== undefined) {
      host = value;
      index += 1;
    } else {
      throw new Error('Expected --project-root <absolute-project-directory> [--host auto|codex|zcode].');
    }
  }
  if (projectRoot === undefined) {
    throw new Error('Expected --project-root <absolute-project-directory>.');
  }
  console.log(JSON.stringify(install(projectRoot, { host }), null, 2));
}

module.exports = { install, resolveHost };
if (require.main === module) {
  try {
    main(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
