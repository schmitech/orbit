# Multilingual Chat Support

This document explains the multilingual chat support functionality that automatically detects the language of a user's query and instructs the LLM to respond in the same language.

## Overview

The chat service includes language detection capability that:

1. Detects the language of the user's input query
2. Modifies the system prompt to include instructions for the LLM to respond in the same language
3. Creates a temporary system prompt with these language instructions
4. Uses this enhanced prompt for generating the response

This functionality can be enabled/disabled through configuration and requires no additional setup when enabled.

## Configuration

Language detection can be configured in the `config.yaml` file:

```yaml
general:
  language_detection: true  # Enable/disable language detection
  verbose: false           # Enable detailed logging for debugging
```

## Architecture

The language detection system consists of two main components:

1. `LanguageDetector` class in `server/utils/language_detector.py`
2. Language detection integration in `ChatService` class in `server/services/chat_service.py`

### LanguageDetector

The `LanguageDetector` class provides robust language detection using an ensemble approach:

1. **Multiple Detection Libraries**:
   - Primary: `langdetect` (with confidence scores)
   - Secondary: `langid` (better for technical text)
   - Tertiary: `pycld2` (good for short texts)

2. **Detection Strategies**:
   - Ensemble voting with weighted confidence
   - Character frequency analysis for Latin-script languages
   - Script analysis for CJK and other writing systems
   - Special handling for short texts and product names

3. **Key Features**:
   - Handles short texts (as few as 5 characters)
   - Supports technical content and product descriptions
   - Provides confidence scores for detections
   - Fallback mechanisms for edge cases

### ChatService Integration

The `ChatService` integrates language detection into the chat flow:

1. **Initialization**:
   ```python
   self.language_detection_enabled = _is_true_value(config.get('general', {}).get('language_detection', True))
   if self.language_detection_enabled:
       self.language_detector = LanguageDetector(verbose=self.verbose)
   ```

2. **Prompt Enhancement**:
   - Detects language using `LanguageDetector`
   - Enhances system prompt with language-specific instructions
   - Uses language names from `pycountry` or fallback mapping
   - Creates temporary prompt override for non-English responses

## Implementation Details

### Language Detection Process

1. **Text Preprocessing**:
   - Removes excess whitespace
   - Handles very short texts (< 5 characters)
   - Detects English wh-questions
   - Analyzes character statistics

2. **Script Analysis**:
   - Identifies writing system (Latin, Cyrillic, CJK, Arabic)
   - Calculates script ratios for mixed-script text
   - Special handling for CJK languages

3. **Ensemble Detection**:
   - Uses multiple detection libraries
   - Applies weighted voting based on confidence
   - Generates text variations for short texts
   - Handles technical content and product names

4. **Confidence Handling**:
   - Minimum confidence threshold (default: 0.7)
   - Fallback to English for low confidence
   - Special rules for short texts and product listings

### Prompt Enhancement Process

1. **Language Detection**:
   ```python
   detected_lang = self.language_detector.detect(message)
   ```

2. **Language Name Resolution**:
   - Uses `pycountry` for ISO code to language name conversion
   - Fallback to common language mapping
   - Handles unknown language codes gracefully

3. **Prompt Modification**:
   ```python
   enhanced_prompt = f"""{original_prompt}

IMPORTANT: The user's message is in {language_name}. You MUST respond in {language_name} only."""
   ```

4. **Temporary Override**:
   - Sets enhanced prompt on LLM client
   - Clears override after response generation
   - Preserves original prompt for future use

## Supported Languages

The language detector can identify many languages, with particularly good support for:

- English (en)
- Spanish (es)
- French (fr)
- German (de)
- Italian (it)
- Portuguese (pt)
- Russian (ru)
- Chinese (zh)
- Japanese (ja)
- Korean (ko)
- Arabic (ar)
- Hindi (hi)

## Performance Considerations

1. **Detection Accuracy**:
   - High accuracy for texts > 20 characters
   - Special handling for short texts
   - Confidence-based fallbacks

2. **Resource Usage**:
   - Minimal memory footprint
   - Efficient character analysis
   - Lazy loading of detection libraries

3. **Edge Cases**:
   - Product names and technical terms
   - Mixed-language content
   - Short queries and commands

## Testing and Debugging

1. **Verbose Mode**:
   - Enable detailed logging with `verbose: true`
   - Logs detection steps and confidence scores
   - Shows prompt enhancement details

2. **Demo Script**:
   - Located in `server/test/language_detection_demo.py`
   - Demonstrates detection with various inputs
   - Shows confidence scores and fallbacks

3. **Test Suite**:
   - Located in `server/tests/test_language_detector.py`
   - Covers various edge cases
   - Tests ensemble detection accuracy

## Best Practices

1. **Configuration**:
   - Enable language detection in production
   - Use verbose mode for debugging
   - Monitor detection accuracy

2. **Error Handling**:
   - Graceful fallback to English
   - Logging of detection failures
   - Clear error messages

3. **Performance**:
   - Monitor detection latency
   - Watch for memory usage
   - Profile ensemble detection