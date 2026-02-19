# Testing Guide for @schmitech/markdown-renderer

## Quick Start Testing

### 1. Install Dependencies and Run Test Server

```bash
# Install dependencies
npm install

# Run the test server (includes demo app)
npm run test
```

Then open http://localhost:3333 in your browser.

### 2. Test the Built Package

```bash
# Build the package
npm run build

# Test the built version
npm run test:build
```

Then open http://localhost:3334 in your browser.

## What to Test

### ✅ Basic Markdown Features
- Headers (H1-H6)
- Bold, italic, and combined formatting
- Lists (ordered and unordered)
- Links
- Code blocks and inline code
- Blockquotes
- Horizontal rules

### ✅ Tables (GitHub Flavored Markdown)
- Basic tables
- Aligned columns
- Long content in cells

### ✅ Math Notation
- Inline math: `$x^2$`
- Display math: `$$\int_0^1 x dx$$`
- Complex equations
- Greek letters and symbols

### ✅ Chemistry Notation
- Chemical formulas: `$\ce{H2O}$`
- Chemical equations
- Organic chemistry structures

### ✅ Currency Handling
- Verify `$100` displays as currency
- Verify `$x$` displays as math variable
- Test ranges like `$100-$500`
- Test with thousands separator: `$1,234.56`

### ✅ Edge Cases
- Mixed currency and math in same paragraph
- Escaped characters
- Empty math blocks
- Very long content (stress test)

## Integration Testing

### Test in chat-widget

```bash
cd ../chat-widget
npm install
npm run dev
```

### Test in chat-app

```bash
cd ../chat-app
npm install  
npm run dev
```

## Verify Package Exports

After building, check that the following files exist:
- `dist/markdown-renderer.es.js` - ES module
- `dist/markdown-renderer.umd.js` - UMD module
- `dist/index.d.ts` - TypeScript definitions
- `dist/MarkdownStyles.css` - Styles

## Browser Compatibility

Test in:
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Performance Checklist

- [ ] Page loads quickly
- [ ] Typing in custom input is responsive
- [ ] Switching between test cases is instant
- [ ] Stress test renders without freezing
- [ ] Math equations render correctly
- [ ] No console errors

## Common Issues to Watch For

1. **Math not rendering**: Check if KaTeX CSS is loaded
2. **Styles missing**: Verify `@schmitech/markdown-renderer/styles` import
3. **Currency showing as math**: Test the preprocessing logic
4. **Chemistry formulas not working**: Ensure mhchem.js is loaded

## Publishing Checklist

Before publishing to npm:

1. [ ] All tests pass
2. [ ] Build completes without errors
3. [ ] Integration with chat-widget works
4. [ ] Integration with chat-app works
5. [ ] README is up to date
6. [ ] Version number is correct
7. [ ] Package.json has all required fields

## Commands Summary

```bash
# Development
npm run dev        # Start dev server
npm run test       # Run test app

# Building
npm run build      # Build the package
npm run test:build # Test built package

# Quality
npm run lint       # Run linter
npm run build:types # Build TypeScript definitions only
```