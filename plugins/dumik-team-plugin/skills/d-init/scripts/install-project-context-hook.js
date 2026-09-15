#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const LOADER_NAME = 'dumik-project-context.cjs';
const STATUS_MESSAGE = 'Loading DUMIK project context';
const source = path.resolve(__dirname, '../../../hooks/load-project-context.js');
const { isWithin } = require(source);

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

function install(rootPath) {
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

  const configPath = path.join(root, '.codex/hooks.json');
  const loaderPath = path.join(root, '.codex/hooks', LOADER_NAME);
  assertLocalPath(root, configPath);
  assertLocalPath(root, loaderPath);
  const before = fs.existsSync(configPath) ? fs.readFileSync(configPath, 'utf8') : null;
  const config = before === null ? { hooks: {} } : JSON.parse(before.replace(/^\uFEFF/, ''));
  if (!config || typeof config !== 'object' || Array.isArray(config) ||
      (config.hooks !== undefined &&
       (!config.hooks || typeof config.hooks !== 'object' || Array.isArray(config.hooks)))) {
    throw new Error('Existing hooks.json has an unsupported structure; it was not changed.');
  }
  config.hooks ??= {};
  const groups = config.hooks.SessionStart ?? [];
  if (!Array.isArray(groups) || groups.some((group) =>
    !group || typeof group !== 'object' || !Array.isArray(group.hooks))) {
    throw new Error('Existing SessionStart configuration was not changed.');
  }

  const loaderText = fs.readFileSync(source, 'utf8');
  if (fs.existsSync(loaderPath) && fs.readFileSync(loaderPath, 'utf8') !== loaderText) {
    throw new Error(`Existing ${LOADER_NAME} differs; preserve it and resolve the change explicitly.`);
  }
  const portablePath = loaderPath.replace(/\\/g, '/');
  const handler = {
    type: 'command',
    command: `node ${quotePosix(portablePath)}`,
    commandWindows: `node ${quotePowerShell(portablePath)}`,
    timeout: 3,
    additionalContextLimit: 8000,
    statusMessage: STATUS_MESSAGE,
  };
  const matcher = 'startup|resume|clear|compact';
  const managedGroups = groups.filter((group) => group.hooks.some((item) =>
    item && (item.statusMessage === STATUS_MESSAGE ||
      (typeof item.command === 'string' && item.command.includes(LOADER_NAME)))));

  let configChanged = false;
  if (managedGroups.length) {
    const existing = managedGroups[0];
    if (managedGroups.length !== 1 || existing.matcher !== matcher ||
        existing.hooks.length !== 1 ||
        JSON.stringify(existing.hooks[0]) !== JSON.stringify(handler)) {
      throw new Error('An existing DUMIK context hook differs; it was not overwritten or duplicated.');
    }
  } else {
    config.hooks.SessionStart = [...groups, { matcher, hooks: [handler] }];
    configChanged = true;
  }

  fs.mkdirSync(path.dirname(loaderPath), { recursive: true });
  assertLocalPath(root, configPath);
  assertLocalPath(root, loaderPath);
  const current = fs.existsSync(configPath) ? fs.readFileSync(configPath, 'utf8') : null;
  if (current !== before) throw new Error('hooks.json changed during installation; retry after reviewing it.');
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
    hookConfig: configPath,
    loader: loaderPath,
    activation: 'requires-hook-trust',
  };
}

function main(argv) {
  if (argv.length === 1 && ['--help', '-h'].includes(argv[0])) {
    console.log('Usage: node install-project-context-hook.js --project-root <absolute-project-directory>');
    return;
  }
  if (argv.length !== 2 || argv[0] !== '--project-root') {
    throw new Error('Expected --project-root <absolute-project-directory>.');
  }
  console.log(JSON.stringify(install(argv[1]), null, 2));
}

module.exports = { install };
if (require.main === module) {
  try {
    main(process.argv.slice(2));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
