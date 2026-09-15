const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { test } = require('node:test');

const installer = path.resolve(__dirname, '../install-project-context-hook.js');
const loaderModule = path.resolve(__dirname, '../../../../hooks/load-project-context.js');

function fixture(t) {
  const tempRoot = fs.realpathSync(os.tmpdir());
  const base = fs.mkdtempSync(path.join(tempRoot, 'dumik-context-test-'));
  t.after(() => {
    assert.equal(path.dirname(base), tempRoot);
    assert.ok(path.basename(base).startsWith('dumik-context-test-'));
    fs.rmSync(base, { recursive: true, force: true });
  });
  const root = path.join(base, 'project with spaces');
  fs.mkdirSync(root);
  fs.writeFileSync(path.join(root, 'AGENTS.md'), '# Project rules\nPreserve this.\n');
  fs.writeFileSync(path.join(root, 'design.md'), '# Design\nProduct reference only.\n');
  return {
    base,
    root,
    config: path.join(root, '.codex/hooks.json'),
    loader: path.join(root, '.codex/hooks/dumik-project-context.cjs'),
  };
}

function install(f) {
  return spawnSync(process.execPath, [installer, '--project-root', f.root], {
    encoding: 'utf8',
    timeout: 3000,
  });
}

function run(f, event = {}, cwd = f.root) {
  return spawnSync(process.execPath, [f.loader], {
    cwd,
    input: JSON.stringify({
      cwd,
      source: 'startup',
      hook_event_name: 'SessionStart',
      ...event,
    }),
    encoding: 'utf8',
    timeout: 3000,
  });
}

test('installs a project-scoped hook without changing project documents', (t) => {
  const f = fixture(t);
  const agents = fs.readFileSync(path.join(f.root, 'AGENTS.md'));
  const design = fs.readFileSync(path.join(f.root, 'design.md'));
  const result = install(f);
  assert.equal(result.status, 0, result.stderr);
  const config = JSON.parse(fs.readFileSync(f.config, 'utf8'));
  const handler = config.hooks.SessionStart[0].hooks[0];
  assert.match(handler.command, /dumik-project-context\.cjs/);
  assert.match(handler.commandWindows, /dumik-project-context\.cjs/);
  assert.equal(handler.type, 'command');
  assert.equal(handler.additionalContextLimit, 8000);
  assert.ok(fs.existsSync(f.loader));
  assert.deepEqual(fs.readFileSync(path.join(f.root, 'AGENTS.md')), agents);
  assert.deepEqual(fs.readFileSync(path.join(f.root, 'design.md')), design);
  assert.equal(JSON.parse(result.stdout).activation, 'requires-hook-trust');
});

test('merges existing hooks and is idempotent', (t) => {
  const f = fixture(t);
  const existing = {
    description: 'User-owned hooks',
    hooks: {
      SessionStart: [{ hooks: [{ type: 'command', command: 'echo existing' }] }],
      Stop: [{ hooks: [{ type: 'command', command: 'echo stop' }] }],
    },
  };
  fs.mkdirSync(path.dirname(f.config));
  fs.writeFileSync(f.config, JSON.stringify(existing));
  assert.equal(install(f).status, 0);
  const first = fs.readFileSync(f.config, 'utf8');
  const next = install(f);
  assert.equal(next.status, 0, next.stderr);
  assert.equal(fs.readFileSync(f.config, 'utf8'), first);
  const actual = JSON.parse(first);
  assert.deepEqual(actual.hooks.Stop, existing.hooks.Stop);
  assert.deepEqual(actual.hooks.SessionStart[0], existing.hooks.SessionStart[0]);
  assert.equal(actual.hooks.SessionStart.length, 2);
  assert.equal(actual.description, existing.description);
  assert.equal(JSON.parse(next.stdout).status, 'unchanged');
});

test('rejects a relative project path', () => {
  const result = spawnSync(process.execPath, [installer, '--project-root', '.'], {
    encoding: 'utf8',
  });
  assert.notEqual(result.status, 0);
});

test('missing project documents do not fall back to parent documents', (t) => {
  const f = fixture(t);
  fs.unlinkSync(path.join(f.root, 'design.md'));
  fs.writeFileSync(path.join(f.base, 'design.md'), '# Parent must not be used');
  const result = install(f);
  assert.notEqual(result.status, 0);
  assert.equal(fs.existsSync(f.config), false);
});

test('invalid existing JSON remains untouched', (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.dirname(f.config));
  fs.writeFileSync(f.config, '{broken');
  assert.notEqual(install(f).status, 0);
  assert.equal(fs.readFileSync(f.config, 'utf8'), '{broken');
  assert.equal(fs.existsSync(f.loader), false);
});

test('custom loader content is not overwritten', (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.dirname(f.loader), { recursive: true });
  fs.writeFileSync(f.loader, '// User-owned content\n');
  assert.notEqual(install(f).status, 0);
  assert.equal(fs.readFileSync(f.loader, 'utf8'), '// User-owned content\n');
  assert.equal(fs.existsSync(f.config), false);
});

test('loads the bound project from nested working directories', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  const nested = path.join(f.root, 'work/nested');
  fs.mkdirSync(nested, { recursive: true });
  fs.writeFileSync(path.join(nested, 'AGENTS.md'), 'Not the selected root document.');
  const result = run(f, {}, nested);
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.systemMessage, undefined);
  assert.equal(output.hookSpecificOutput.hookEventName, 'SessionStart');
  assert.doesNotMatch(output.hookSpecificOutput.additionalContext, /Preserve this/);
  assert.match(output.hookSpecificOutput.additionalContext, /Product reference only/);
  assert.doesNotMatch(output.hookSpecificOutput.additionalContext, /Not the selected/);
});

test('does not load the project for a sibling working directory', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  const sibling = `${f.root}-other`;
  fs.mkdirSync(sibling);
  const result = run(f, {}, sibling);
  assert.equal(result.status, 0);
  assert.equal(result.stdout, '');
});

test('invalid input or other events produce no context', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  assert.equal(run(f, { hook_event_name: 'Stop' }).stdout, '');
  assert.equal(run(f, { cwd: null }).stdout, '');
  const broken = spawnSync(process.execPath, [f.loader], {
    cwd: f.root,
    input: '{bad',
    encoding: 'utf8',
    timeout: 3000,
  });
  assert.equal(broken.status, 0);
  assert.equal(broken.stdout, '');
});

test('all documented SessionStart sources return current file contents', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  for (const source of ['startup', 'resume', 'clear', 'compact']) {
    fs.writeFileSync(path.join(f.root, 'design.md'), `Design at ${source}`);
    const result = run(f, { source });
    assert.equal(result.status, 0);
    assert.ok(JSON.parse(result.stdout).hookSpecificOutput.additionalContext.includes(`Design at ${source}`));
  }
});

test('removed design file is reported without loading a parent substitute', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  fs.unlinkSync(path.join(f.root, 'design.md'));
  fs.writeFileSync(path.join(f.base, 'design.md'), 'Parent substitute');
  const output = JSON.parse(run(f).stdout).hookSpecificOutput.additionalContext;
  assert.match(output, /design\.md.*not loaded/);
  assert.doesNotMatch(output, /Parent substitute/);
});

test('large UTF-8 files are bounded without splitting characters', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  fs.writeFileSync(path.join(f.root, 'design.md'), '\u949b'.repeat(100000));
  const output = JSON.parse(run(f).stdout).hookSpecificOutput.additionalContext;
  assert.ok(Buffer.byteLength(output, 'utf8') < 35000);
  assert.match(output, /TRUNCATED/);
  assert.doesNotMatch(output, /\uFFFD/);
});

test('a linked input outside the project is not read', (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  const external = path.join(f.base, 'external.md');
  fs.writeFileSync(external, 'External content must not load');
  fs.unlinkSync(path.join(f.root, 'design.md'));
  try {
    fs.symlinkSync(external, path.join(f.root, 'design.md'));
  } catch (error) {
    if (error.code === 'EPERM') return t.skip('File symlinks unavailable on this host');
    throw error;
  }
  const output = JSON.parse(run(f).stdout).hookSpecificOutput.additionalContext;
  assert.doesNotMatch(output, /External content must not load/);
  assert.match(output, /not loaded/);
});

test('an existing linked .codex directory outside the project is rejected', (t) => {
  const f = fixture(t);
  const external = path.join(f.base, 'external-config');
  fs.mkdirSync(external);
  fs.symlinkSync(external, path.join(f.root, '.codex'), 'junction');
  const result = install(f);
  assert.notEqual(result.status, 0);
  assert.deepEqual(fs.readdirSync(external), []);
});

test('an open stdin pipe cannot hang the loader', async (t) => {
  const f = fixture(t);
  assert.equal(install(f).status, 0);
  const child = spawn(process.execPath, [f.loader], { cwd: f.root, stdio: 'pipe' });
  let output = '';
  child.stdout.on('data', (chunk) => { output += chunk; });
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('Loader did not exit with an open stdin pipe'));
    }, 2000);
    child.on('error', (error) => { clearTimeout(timer); reject(error); });
    child.on('exit', (code) => {
      clearTimeout(timer);
      assert.equal(code, 0);
      resolve();
    });
  });
  assert.equal(output, '');
});

test('loader can be imported without reading stdin or producing output', () => {
  const result = spawnSync(process.execPath, ['-e', `require(${JSON.stringify(loaderModule)});`], {
    input: '',
    encoding: 'utf8',
    timeout: 1500,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, '');
});

test('installed loader works inside a project using ES modules', (t) => {
  const f = fixture(t);
  fs.writeFileSync(path.join(f.root, 'package.json'), '{"type":"module"}');
  assert.equal(install(f).status, 0);
  const result = run(f);
  assert.equal(result.status, 0, result.stderr);
  assert.match(JSON.parse(result.stdout).hookSpecificOutput.additionalContext, /Product reference only/);
  assert.doesNotMatch(JSON.parse(result.stdout).hookSpecificOutput.additionalContext, /Preserve this/);
});

test('only design.md is opened for injection; native AGENTS guidance is not read again', (t) => {
  const f = fixture(t);
  const { buildOutput } = require(loaderModule);
  const opened = [];
  const originalOpen = fs.openSync;
  t.mock.method(fs, 'openSync', (filename, ...args) => {
    opened.push(path.basename(filename));
    return originalOpen.call(fs, filename, ...args);
  });
  const output = buildOutput(f.root, {
    cwd: f.root,
    hook_event_name: 'SessionStart',
    source: 'startup',
  });
  assert.deepEqual(opened, ['design.md']);
  assert.match(output.hookSpecificOutput.additionalContext, /Product reference only/);
  assert.doesNotMatch(output.hookSpecificOutput.additionalContext, /Preserve this/);
});
