import React, { useReducer, useRef, useEffect, useCallback } from 'react';
import { MarkdownRenderer } from '../MarkdownComponents';
import '../MarkdownStyles.css';
import testCases, {
  stressTestContent,
  streamingChartStages,
  multiChartStreamingContent,
  codeSampleLibrary,
} from './testContent';
import type { CodeSample } from './testContent';
import { SampleIntegration } from './SampleIntegration';
import { DebugMath } from './DebugMath';
import './App.css';

type ThemeMode = 'system' | 'light' | 'dark';

type ViewMode =
  | 'testCase'
  | 'custom'
  | 'stressTest'
  | 'integration'
  | 'debug'
  | 'streaming'
  | 'multiChart';

interface AppState {
  viewMode: ViewMode;
  selectedTest: number;
  customContent: string;
  disableMath: boolean;
  showRawOutput: boolean;
  streamingStage: number;
  isStreaming: boolean;
  themeMode: ThemeMode;
  selectedSample: CodeSample | null;
}

type AppAction =
  | { type: 'SELECT_TEST'; index: number }
  | { type: 'SET_VIEW_MODE'; mode: ViewMode }
  | { type: 'SET_CUSTOM_CONTENT'; content: string }
  | { type: 'SET_DISABLE_MATH'; value: boolean }
  | { type: 'SET_SHOW_RAW_OUTPUT'; value: boolean }
  | { type: 'SET_STREAMING_STAGE'; stage: number }
  | { type: 'SET_IS_STREAMING'; value: boolean }
  | { type: 'SET_THEME_MODE'; mode: ThemeMode }
  | { type: 'SELECT_SAMPLE'; sample: CodeSample }
  | { type: 'CLEAR_SAMPLE' }
  | { type: 'START_STREAMING' }
  | { type: 'STOP_STREAMING' };

const initialState: AppState = {
  viewMode: 'testCase',
  selectedTest: 0,
  customContent: '',
  disableMath: false,
  showRawOutput: false,
  streamingStage: 0,
  isStreaming: false,
  themeMode: 'system',
  selectedSample: null,
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SELECT_TEST':
      return {
        ...state,
        viewMode: 'testCase',
        selectedTest: action.index,
        selectedSample: null,
      };
    case 'SET_VIEW_MODE':
      return {
        ...state,
        viewMode: action.mode,
        selectedSample: null,
        // Reset streaming stage when entering streaming mode
        streamingStage: action.mode === 'streaming' ? 0 : state.streamingStage,
      };
    case 'SET_CUSTOM_CONTENT':
      return {
        ...state,
        customContent: action.content,
        selectedSample: null,
      };
    case 'SET_DISABLE_MATH':
      return { ...state, disableMath: action.value };
    case 'SET_SHOW_RAW_OUTPUT':
      return { ...state, showRawOutput: action.value };
    case 'SET_STREAMING_STAGE':
      return { ...state, streamingStage: action.stage };
    case 'SET_IS_STREAMING':
      return { ...state, isStreaming: action.value };
    case 'SET_THEME_MODE':
      return { ...state, themeMode: action.mode };
    case 'SELECT_SAMPLE':
      return {
        ...state,
        viewMode: 'custom',
        customContent: action.sample.markdown,
        selectedSample: action.sample,
      };
    case 'CLEAR_SAMPLE':
      return { ...state, selectedSample: null };
    case 'START_STREAMING':
      return { ...state, streamingStage: 0, isStreaming: true };
    case 'STOP_STREAMING':
      return { ...state, isStreaming: false };
    default:
      return state;
  }
}

const inlineTableTestIndex = testCases.findIndex(
  (test) => test.title === 'LLM Inline Table Response'
);

function App() {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const streamingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const {
    viewMode,
    selectedTest,
    customContent,
    disableMath,
    showRawOutput,
    streamingStage,
    isStreaming,
    themeMode,
    selectedSample,
  } = state;

  const selectedTestCase = testCases[selectedTest];

  // Cleanup streaming interval on unmount
  useEffect(() => {
    return () => {
      if (streamingIntervalRef.current) {
        clearInterval(streamingIntervalRef.current);
      }
    };
  }, []);

  // Determine the effective theme class for the markdown content
  const getThemeClass = (): string => {
    if (themeMode === 'light') return 'light';
    if (themeMode === 'dark') return 'dark';
    return ''; // system preference - no class, CSS handles it
  };

  const currentContent =
    viewMode === 'streaming'
      ? streamingChartStages.stages[streamingStage]
      : viewMode === 'multiChart'
        ? multiChartStreamingContent
        : viewMode === 'stressTest'
          ? stressTestContent
          : viewMode === 'custom'
            ? customContent
            : testCases[selectedTest].content;

  // Start streaming simulation
  const startStreamingSimulation = useCallback(() => {
    dispatch({ type: 'START_STREAMING' });

    let stage = 0;
    streamingIntervalRef.current = setInterval(() => {
      stage++;
      if (stage >= streamingChartStages.stages.length) {
        if (streamingIntervalRef.current) {
          clearInterval(streamingIntervalRef.current);
          streamingIntervalRef.current = null;
        }
        dispatch({ type: 'STOP_STREAMING' });
      } else {
        dispatch({ type: 'SET_STREAMING_STAGE', stage });
      }
    }, 300);
  }, []);

  // Reset to final complete state
  const showCompleteChart = useCallback(() => {
    if (streamingIntervalRef.current) {
      clearInterval(streamingIntervalRef.current);
      streamingIntervalRef.current = null;
    }
    dispatch({ type: 'SET_STREAMING_STAGE', stage: streamingChartStages.stages.length - 1 });
    dispatch({ type: 'STOP_STREAMING' });
  }, []);

  const isTestCaseActive = (index: number) =>
    viewMode === 'testCase' && selectedTest === index;

  return (
    <div className="app">
      <header className="app-header">
        <h1>📝 Markdown Renderer Test Suite</h1>
        <p>Test the @schmitech/markdown-renderer package with various content types</p>
      </header>

      <div className="app-container">
        <aside className="sidebar">
          <h2>Test Cases</h2>

          <div className="test-list">
            {testCases.map((test, index) => (
              <button
                key={index}
                className={`test-button ${isTestCaseActive(index) ? 'active' : ''}`}
                onClick={() => dispatch({ type: 'SELECT_TEST', index })}
              >
                {test.title}
              </button>
            ))}

            {inlineTableTestIndex >= 0 && (
              <button
                className={`test-button inline-table ${isTestCaseActive(inlineTableTestIndex) ? 'active' : ''}`}
                onClick={() => dispatch({ type: 'SELECT_TEST', index: inlineTableTestIndex })}
              >
                🧪 LLM Inline Table
              </button>
            )}

            <button
              className={`test-button stress ${viewMode === 'stressTest' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode: 'stressTest' })}
            >
              🔥 Stress Test
            </button>

            <button
              className={`test-button custom ${viewMode === 'custom' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode: 'custom' })}
            >
              ✏️ Custom Input
            </button>

            <button
              className={`test-button integration ${viewMode === 'integration' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode: 'integration' })}
            >
              💬 Sample Integration
            </button>

            <button
              className={`test-button debug ${viewMode === 'debug' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode: 'debug' })}
            >
              🔍 Debug Math
            </button>

            <button
              className={`test-button streaming ${viewMode === 'streaming' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode: 'streaming' })}
            >
              📊 Chart Streaming
            </button>

            <button
              className={`test-button multichart ${viewMode === 'multiChart' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_VIEW_MODE', mode: 'multiChart' })}
            >
              📈 Multi-Chart Test
            </button>
          </div>

          <div className="options">
            <h3>Options</h3>
            <label className="option">
              <input
                type="checkbox"
                checked={disableMath}
                onChange={(e) => dispatch({ type: 'SET_DISABLE_MATH', value: e.target.checked })}
              />
              Disable Math Rendering
            </label>
            <label className="option">
              <input
                type="checkbox"
                checked={showRawOutput}
                onChange={(e) => dispatch({ type: 'SET_SHOW_RAW_OUTPUT', value: e.target.checked })}
              />
              Show Raw Output
            </label>

            <h3>Theme</h3>
            <div className="theme-selector">
              <label className="theme-option">
                <input
                  type="radio"
                  name="theme"
                  value="system"
                  checked={themeMode === 'system'}
                  onChange={() => dispatch({ type: 'SET_THEME_MODE', mode: 'system' })}
                />
                System
              </label>
              <label className="theme-option">
                <input
                  type="radio"
                  name="theme"
                  value="light"
                  checked={themeMode === 'light'}
                  onChange={() => dispatch({ type: 'SET_THEME_MODE', mode: 'light' })}
                />
                Light
              </label>
              <label className="theme-option">
                <input
                  type="radio"
                  name="theme"
                  value="dark"
                  checked={themeMode === 'dark'}
                  onChange={() => dispatch({ type: 'SET_THEME_MODE', mode: 'dark' })}
                />
                Dark
              </label>
            </div>

            <div className="code-sample-library">
              <h3>Code Sample Library</h3>
              <p className="code-sample-note">
                Load curated snippets to exercise syntax highlighting across ecosystems.
              </p>
              <div className="code-sample-grid">
                {codeSampleLibrary.map((sample) => (
                  <button
                    key={sample.language}
                    className={`code-sample-button ${selectedSample?.language === sample.language ? 'active' : ''}`}
                    onClick={() => dispatch({ type: 'SELECT_SAMPLE', sample })}
                    type="button"
                  >
                    {sample.language}
                  </button>
                ))}
              </div>
              {selectedSample && (
                <div className="code-sample-preview">
                  <strong>{selectedSample.language}</strong>
                  <p>{selectedSample.description}</p>
                  <pre>
                    <code>{selectedSample.preview}</code>
                  </pre>
                  <span className="code-sample-hint">
                    Loaded into Custom Input for further editing.
                  </span>
                </div>
              )}
            </div>
          </div>
        </aside>

        <main className="main-content">
          {viewMode === 'debug' ? (
            <DebugMath />
          ) : viewMode === 'integration' ? (
            <SampleIntegration />
          ) : viewMode === 'streaming' ? (
            <div className="streaming-test-container">
              <h2>📊 Chart Streaming Simulation</h2>
              <p>This test simulates how charts handle streaming data from an LLM response.</p>

              <div className="streaming-controls" style={{
                display: 'flex',
                gap: '10px',
                marginBottom: '20px',
                flexWrap: 'wrap'
              }}>
                <button
                  onClick={startStreamingSimulation}
                  disabled={isStreaming}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: isStreaming ? '#9ca3af' : '#3b82f6',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: isStreaming ? 'not-allowed' : 'pointer'
                  }}
                >
                  {isStreaming ? 'Streaming...' : 'Start Streaming Simulation'}
                </button>

                <button
                  onClick={showCompleteChart}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: '#10b981',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Show Complete Chart
                </button>

                <button
                  onClick={() => dispatch({ type: 'SET_STREAMING_STAGE', stage: 0 })}
                  style={{
                    padding: '8px 16px',
                    backgroundColor: '#f59e0b',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer'
                  }}
                >
                  Reset
                </button>
              </div>

              <div className="streaming-status" style={{
                padding: '10px',
                backgroundColor: '#f3f4f6',
                borderRadius: '4px',
                marginBottom: '15px'
              }}>
                <strong>Stage:</strong> {streamingStage + 1} / {streamingChartStages.stages.length}
                {isStreaming && <span style={{ marginLeft: '10px', color: '#3b82f6' }}>● Streaming</span>}
              </div>
            </div>
          ) : viewMode === 'multiChart' ? (
            <div className="test-info">
              <h2>📈 Multiple Charts - Streaming Stress Test</h2>
              <p>Tests rendering multiple charts simultaneously, common in LLM comprehensive analysis.</p>
            </div>
          ) : viewMode === 'custom' ? (
            <div className="custom-input-container">
              <h2>Custom Markdown Input</h2>
              <textarea
                className="custom-input"
                value={customContent}
                onChange={(e) => dispatch({ type: 'SET_CUSTOM_CONTENT', content: e.target.value })}
                placeholder="Enter your markdown here...

Try:
- Basic markdown: **bold**, *italic*, [links](https://example.com)
- Math: $x^2 + y^2 = z^2$ or $$\int_0^1 x dx$$
- Chemistry: $\ce{H2O}$ or $\ce{CO2}$
- Currency: $100, $1,234.56
- HTML breaks: Why don't skeletons fight each other?<br>They don't have the guts.
- Code blocks with ```
- Tables with | syntax |"
                rows={10}
              />
            </div>
          ) : (
            <div className="test-info">
              <h2>{viewMode === 'stressTest' ? '🔥 Stress Test' : testCases[selectedTest].title}</h2>
              {viewMode === 'testCase' && selectedTestCase?.title === 'LLM Inline Table Response' && (
                <p className="note">
                  This reproduces an LLM response where a table immediately follows punctuation,
                  ensuring our preprocessing still renders the table correctly even when this package
                  is embedded in another application.
                </p>
              )}
              {viewMode === 'testCase' && selectedTestCase?.title === 'Ellipsoid Flattening Math' && (
                <p className="note">
                  Validates inline math variables like $a$, $b$, and $f$ remain math expressions even
                  when surrounded by prose, matching the regression report.
                </p>
              )}
              {viewMode === 'stressTest' && (
                <p className="warning">⚠️ This test contains a large amount of content to test performance</p>
              )}
            </div>
          )}

          {viewMode !== 'integration' && viewMode !== 'debug' && (
            <div className="output-section">
              <div className="output-header">
                <h3>Rendered Output</h3>
                {showRawOutput && (
                  <span className="badge">Raw: {currentContent.length} chars</span>
                )}
              </div>

              <div className={`rendered-output ${themeMode === 'dark' ? 'dark-mode' : themeMode === 'light' ? 'light-mode' : ''}`}>
                <MarkdownRenderer
                  content={currentContent}
                  disableMath={disableMath}
                  className={getThemeClass()}
                />
              </div>

              {showRawOutput && (
                <>
                  <h3>Raw Markdown</h3>
                  <pre className="raw-output">
                    <code>{currentContent}</code>
                  </pre>
                </>
              )}
            </div>
          )}
        </main>
      </div>

      <footer className="app-footer">
        <p>
          Testing <code>@schmitech/markdown-renderer</code> v0.7.4 |
          React {React.version} |
          <a href="https://github.com/schmitech/markdown-renderer" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </p>
      </footer>
    </div>
  );
}

export default App;
