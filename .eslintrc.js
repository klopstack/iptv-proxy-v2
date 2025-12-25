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
    FormData: 'readonly',
    // Shared components defined in base.html
    TagSelector: 'writable'
  },
  // JavaScript rules (for script tags)
  rules: {
    // Console statements are useful for debugging in development
    'no-console': 'off',
    'no-alert': 'off', // Allow alerts/confirms for UI feedback
    // Disable no-unused-vars - functions are called from onclick attributes in HTML
    'no-unused-vars': 'off',
    'no-undef': 'error',
    'no-var': 'error',
    'prefer-const': 'warn',
    // Downgrade eqeqeq to warning for legacy code
    'eqeqeq': 'warn',
    'no-eval': 'error',
    'no-implied-eval': 'error',
    // Allow redeclaring globals that are defined in templates
    'no-redeclare': ['error', { 'builtinGlobals': false }],
    // Disable no-shadow - common pattern in nested functions
    'no-shadow': 'off'
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
        '@html-eslint/no-extra-spacing-attrs': 'off',
        // Disable button-type - not critical for inline buttons
        '@html-eslint/require-button-type': 'off',
        '@html-eslint/no-script-style-type': 'off',
        '@html-eslint/require-img-alt': 'warn',
        // Disable target-blank - we trust our URLs
        '@html-eslint/no-target-blank': 'off',
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
