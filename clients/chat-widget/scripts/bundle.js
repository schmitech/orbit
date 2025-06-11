import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Read the CSS file
const cssContent = fs.readFileSync(path.join(__dirname, '../dist/chatbot-widget.css'), 'utf8');

// Read the JS file
const jsContent = fs.readFileSync(path.join(__dirname, '../dist/chatbot-widget.umd.js'), 'utf8');

// Create the combined content
const combinedContent = `
// Add CSS to the document
(function() {
  const style = document.createElement('style');
  style.textContent = \`${cssContent}\`;
  document.head.appendChild(style);
})();

${jsContent}
`;

// Write the combined file
fs.writeFileSync(path.join(__dirname, '../dist/chatbot-widget.bundle.js'), combinedContent);

console.log('Successfully created chatbot-widget.bundle.js'); 