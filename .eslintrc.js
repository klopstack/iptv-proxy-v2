module.exports = {
  env: {
    browser: true,
    es6: true
  },
  parserOptions: {
    ecmaVersion: 2020,
    sourceType: 'script'
  },
  plugins: ['html'],
  globals: {
    // Bootstrap 5 globals
    bootstrap: 'readonly',
    // Commonly used browser globals
    fetch: 'readonly',
    alert: 'readonly',
    confirm: 'readonly',
    FormData: 'readonly'
  },
  // JavaScript rules (for script tags)
  rules: {
    'no-console': 'warn',
    'no-alert': 'off', // Allow alerts/confirms for UI feedback
    'no-unused-vars': ['error', {
      'varsIgnorePattern': '^_',
      'argsIgnorePattern': '^_'
    }],
    'no-undef': 'error',
    'no-var': 'error',
    'prefer-const': 'warn',
    'eqeqeq': 'error',
    'no-eval': 'error',
    'no-implied-eval': 'error',
    'no-redeclare': 'error',
    'no-shadow': 'warn'
  },
  overrides: [
    {
      // HTML structure validation
      files: ['*.html'],
      parser: '@html-eslint/parser',
      plugins: ['@html-eslint'],
      extends: ['plugin:@html-eslint/recommended'],
      rules: {
        // HTML structure rules
        '@html-eslint/require-doctype': 'off',
        '@html-eslint/no-inline-styles': 'off',
        '@html-eslint/indent': 'off', // Templates have their own style
        '@html-eslint/attrs-newline': 'off', // Allow attributes on same line
        '@html-eslint/element-newline': 'off', // Allow flexible element spacing
        '@html-eslint/require-closing-tags': 'error',
        '@html-eslint/no-duplicate-attrs': 'error',
        '@html-eslint/no-duplicate-id': 'error',
        '@html-eslint/no-obsolete-tags': 'error',
        '@html-eslint/require-li-container': 'error',
        '@html-eslint/no-extra-spacing-attrs': 'warn',
        '@html-eslint/require-button-type': 'warn',
        '@html-eslint/no-script-style-type': 'warn',
        '@html-eslint/require-img-alt': 'warn',
        '@html-eslint/no-target-blank': 'warn',
        '@html-eslint/require-meta-charset': 'off'
      }
    }
  ],
  settings: {
    'html/html-extensions': ['.html'],
    'html/indent': '0',
    'html/report-bad-indent': 'off'
  }
};
