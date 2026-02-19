# @schmitech/markdown-renderer

A shared React markdown renderer component with built-in support for math notation (via KaTeX) and chemistry formulas.

## Features

- Full markdown support via `react-markdown`
- Math notation rendering with KaTeX
- Chemistry formula support (mhchem)
- Currency handling (distinguishes between $5 and $x$ math notation)
- GitHub Flavored Markdown (GFM) support
- Customizable styling

## Installation

```bash
npm install @schmitech/markdown-renderer
```

## Usage

### React setup

In React applications (Vite, CRA, Next.js, etc.) simply import the component. The
library injects its base `.markdown-content` styles automatically when it first
loads. If your setup performs server-side rendering or you need manual control,
you can call the exported `ensureStylesInjected()` helper explicitly. Consumers
who prefer to handle CSS separately can still import
`import '@schmitech/markdown-renderer/styles';`.

### Basic Usage

```tsx
import { MarkdownRenderer } from '@schmitech/markdown-renderer';
// Base styles are injected automatically. If you want explicit control, add:
// import '@schmitech/markdown-renderer/styles';

function MyComponent() {
  const content = `
# Hello World

This is a **markdown** example with math: $x^2 + y^2 = z^2$

And chemistry: $\\ce{H2O}$
  `;

  return <MarkdownRenderer content={content} />;
}
```

### With Custom Styling

```tsx
import { MarkdownRenderer } from '@schmitech/markdown-renderer';

function MyComponent() {
  return (
    <MarkdownRenderer 
      content="# Hello" 
      className="my-custom-class"
    />
  );
}
```

### Disable Math Rendering

```tsx
<MarkdownRenderer 
  content="Some content" 
  disableMath={true}
/>
```

## API

### MarkdownRenderer Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| content | string | required | The markdown content to render |
| className | string | '' | Additional CSS classes to apply |
| disableMath | boolean | false | Disable math notation rendering |

### Exported Utilities

- `preprocessMarkdown(content: string): string` - Preprocesses markdown content for proper math/currency handling
- `containsMathNotation(text: string): boolean` - Checks if text contains math notation
- `MarkdownLink` - Custom link component that opens in new tabs

## Styling

The base stylesheet loads automatically when you import the library. You can also
pull it in manually if your bundler requires explicit CSS imports or you need to
override the defaults in a dedicated file:

```tsx
import '@schmitech/markdown-renderer/styles';
```

Or reference the built CSS directly from your own stylesheets:

```css
@import '@schmitech/markdown-renderer/dist/MarkdownStyles.css';
```

If you are rendering on the server (Next.js, Remix, etc.) you may want to call
`ensureStylesInjected()` in a `useEffect` on the client to guarantee the base
stylesheet is present.

To customize the look, add your own selectors that target the generated
`markdown-content` wrapper:

```css
.markdown-content h1 {
  color: #7c3aed;
}
```

## License

Apache 2.0
