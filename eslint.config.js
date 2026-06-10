// Flat ESLint config — correctness only, for the site's AUTHORED browser JS.
//
// Scope (deliberately tiny): the hand-authored JS source is just the
// templates/*.template.js build inputs plus the one hand-authored shipped file
// public/verify/verify.js. Everything else under public/ is GENERATED and SIGNED
// (hashed in integrity.json) and must never be linted or reformatted.
//
// Formatting is owned by Prettier + .editorconfig, so no stylistic rules here.

import js from '@eslint/js';
import globals from 'globals';

const browserGlobals = {
  ...globals.browser,
  ...globals.serviceworker,
  ...globals.es2020,
  trustedTypes: 'readonly',
};

// the ONLY authored JS in scope. every other .js in the repo (generated public/
// bundles, archived *.v*.js, docs backups) is out of scope by omission — each
// config below is files-scoped, so nothing else is linted.
const TARGETS = ['templates/**/*.template.js', 'public/verify/verify.js'];

export default [
  { ignores: ['node_modules/**', '_archives/**'] },
  { ...js.configs.recommended, files: TARGETS },
  {
    files: TARGETS,
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'script',
      globals: browserGlobals,
    },
    rules: {
      // real bugs — these are the point of the linter.
      'no-undef': 'error',
      'no-redeclare': 'error',
      'no-unreachable': 'error',
      'no-dupe-keys': 'error',
      'no-dupe-args': 'error',
      // allow the deliberate `while ((m = re.exec(s)))` parenthesised form.
      'no-cond-assign': ['error', 'except-parens'],
      'no-constant-condition': ['error', { checkLoops: false }],
      'no-self-assign': 'error',
      'use-isnan': 'error',
      'valid-typeof': 'error',
      // the site uses `try { … } catch (_) {}` deliberately as defensive,
      // ignore-on-failure guards (storage, JSON, optional APIs). that is
      // intentional, not a bug — allow the empty catch.
      'no-empty': ['error', { allowEmptyCatch: true }],
      // `_` covers the deliberate catch (_) ignore-guards as well as args/vars.
      'no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
      // smart: strict comparison everywhere except the deliberate `== null`
      // null-or-undefined idiom the codebase uses throughout.
      eqeqeq: ['error', 'smart'],
      // formatting is Prettier's job; don't fight the existing editorial style.
      'curly': 'off',
    },
  },
];
