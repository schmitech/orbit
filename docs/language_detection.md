# Multilingual Chat Support

This document explains the multilingual chat support functionality that automatically detects the language of a user's query and instructs the LLM to respond in the same language.

## Overview

The chat service includes an advanced language detection capability that:

* Detects the language of the user's input query with high accuracy
* Analyzes the script type (Latin, Cyrillic, CJK, Arabic, etc.)
* Provides confidence scores and detailed detection results
* Modifies the system prompt to include language-specific instructions
* Ensures the LLM responds in the detected language

This functionality can be enabled/disabled through configuration and requires no additional setup when enabled.

## Configuration

Language detection can be configured in the `config.yaml` file.

## Architecture

The enhanced language detection system consists of a modular architecture with specialized components.

### Core Components

1.  **`LanguageDetector`** - Main orchestrator class
2.  **`LanguagePatternRepository`** - Centralized pattern storage
3.  **`ScriptAnalyzer`** - Script type detection
4.  **`TextAnalyzer`** - Text preprocessing and analysis
5.  **`ConfidenceCalculator`** - Sophisticated confidence scoring
6.  **Specialized Detectors** - Language-specific detection logic
7.  **Detection Backends** - Interfaces to detection libraries

### Component Details

#### 1. LanguagePatternRepository
Centralizes all language-specific patterns:
* **Starters**: Common beginning words (e.g., "what", "when", "how")
* **Phrases**: Multi-word patterns (e.g., "can you", "how to")
* **Accents**: Language-specific characters
* **Indicators**: Unique language markers
* **Character frequencies**: Statistical patterns

#### 2. ScriptAnalyzer
Advanced script detection using:
* **Unicode ranges**: Precise character classification
* **Script ratios**: Handles mixed-script texts
* **Supported scripts**: Latin, Cyrillic, CJK, Arabic, Hebrew, Greek, Devanagari

#### 3. TextAnalyzer
Comprehensive text analysis:
* **Character statistics**: Alpha, digit, punctuation ratios
* **Text variations**: Generates alternatives for better detection
* **N-gram extraction**: Pattern analysis
* **Entropy calculation**: Text complexity metrics
* **Code detection**: Identifies technical content

#### 4. Specialized Detectors
Language-specific detection logic:
* **EnglishDetector**: Quick English identification
* **CyrillicLanguageDetector**: Distinguishes Russian, Mongolian, etc.
* **CJK handlers**: Separate Chinese, Japanese, Korean

#### 5. Detection Backends
Clean interfaces for multiple libraries:
* **LangDetectBackend**: Primary detector with probabilistic approach
* **LangIdBackend**: Secondary detector, good for technical text
* **PyCLD2Backend**: Tertiary detector, excellent for short texts

### ChatService Integration

The `ChatService` seamlessly integrates the enhanced language detection.

1.  **Initialization**: The service initializes the `LanguageDetector` based on configuration settings.
    ```python
    self.language_detection_enabled = config.get('general', {}).get('language_detection', True)
    if self.language_detection_enabled:
        self.language_detector = LanguageDetector(
            verbose=self.verbose,
            min_confidence=config.get('general', {}).get('min_confidence', 0.7)
        )
    ```
2.  **Detection with Details**: Before generating a response, the service calls the detector.
    ```python
    result = self.language_detector.detect_with_details(message)
    if result.confidence >= self.min_confidence:
        # Use detected language
        language_code = result.language
    else:
        # Fallback to English
        language_code = 'en'
    ```
3.  **Enhanced Prompt Generation**: The system prompt is modified to instruct the LLM to respond in the detected language, with graceful handling for low-confidence scenarios.

## Enhanced Features

### 1. Detection Results
The `DetectionResult` class provides a detailed output for every detection.
```python
@dataclass
class DetectionResult:
    language: str           # ISO 639-1 code
    confidence: float       # 0.0 to 1.0
    script: ScriptType      # Detected script type
    method: str            # Detection method used
    details: Dict[str, Any] # Additional information
```

### 2. Confidence Scoring
The system uses a multi-factor confidence calculation for higher accuracy:
* **Ensemble voting**: It combines weighted votes from the `LangDetect`, `LangId`, and `PyCLD2` backends.
* **Pattern matching**: The score is significantly boosted by the presence of language-specific indicators and patterns.
* **Vote margin**: The difference between the top two language candidates is used to adjust confidence.
* **Text features**: Final score adjustments are made based on text length, script purity, and content type.

### 3. Script Detection
Advanced Unicode-based script analysis provides deep insight into the text's composition:
* **Primary script identification**: Determines the dominant writing system.
* **Mixed script handling**: Calculates the percentage of each script in the text.
* **CJK disambiguation**: Precisely separates Chinese, Japanese, and Korean based on unique characters and particles.
* **Special scripts**: Full support for Arabic, Hebrew, Devanagari, and more.

### 4. Pattern-Based Enhancement
The detector's accuracy is enhanced by a sophisticated pattern-matching engine that uses precise, word-boundary-aware checks to avoid false positives.
* **Quick detection**: Fast paths are used for common, unambiguous English patterns.
* **Accent analysis**: The presence of language-specific accented characters provides a strong signal.
* **Phrase matching**: Common multi-word patterns are identified for higher accuracy.
* **Statistical analysis**: Character frequency patterns are used as a secondary signal.

## Implementation Details

### Detection Process Flow

1.  **Pre-processing**: Input text is cleaned and validated. Texts shorter than 3 characters use a default result.
2.  **Quick Checks**: The text is first run through a high-speed English detector to identify common cases immediately.
3.  **Script Analysis**: The writing system is analyzed. If the script is CJK, Arabic, or another non-Latin script, specialized handlers are used to make a determination.
4.  **Ensemble Detection**: For Latin-based scripts, a vote is taken from all enabled backends. The votes are weighted and heavily adjusted based on pattern-matching results.
5.  **Confidence Calculation**: A final, sophisticated confidence score is calculated based on the voting consensus, pattern boosts, and overall text features.

## Supported Languages

The detector provides excellent support across three tiers of accuracy.

### Tier 1 (Highest Accuracy)
* English (en)
* Spanish (es)
* French (fr)
* German (de)
* Chinese (zh)
* Japanese (ja)
* Korean (ko)

### Tier 2 (Very Good)
* Italian (it)
* Portuguese (pt)
* Russian (ru)
* Arabic (ar)

### Tier 3 (Good)
* Dutch (nl)
* Polish (pl)
* Swedish (sv)
* Turkish (tr)
* Mongolian (mn)
* Greek (el)
* Hebrew (he)

## Testing and Debugging

### Verbose Mode
Enable `verbose: true` in `config.yaml` to see detailed logs, including backend voting, pattern matches, and confidence calculations.

### Test Suite
The system includes a comprehensive and robust test suite to ensure accuracy and reliability. The tests have been enhanced to be stricter, cover more languages and edge cases, and verify high confidence scores for unambiguous detections.
* **Unit tests**: `pytest server/tests/test_language_detector.py`
* **Integration tests**: `pytest server/tests/test_chat_service_multilingual.py`
* **Performance tests**: `python server/tests/benchmark_language_detection.py`

### Demo Script
An interactive demo script is available for real-time testing and visualization of detection results.
* Run with: `python server/test/language_detection_demo.py`