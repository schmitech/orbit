# Language Detection Enhancement Roadmap

## Overview
This document outlines the future direction for enhancing the language detection system in `server/inference/pipeline/steps/language_detection.py`. The initial implementation phase is complete, and this roadmap details the next steps for architectural improvements, advanced features, and broader language support.

## Current State
The language detection step is now a robust, configurable system that provides a strong foundation for future work. Key implemented features include:

- **Multi-Backend Ensemble Detection:** The system uses a weighted-voting ensemble of `langdetect`, `langid`, and `pycld2` for high-accuracy detection. Backends are configurable and handle failures gracefully.
- **Confidence Scoring:** All detections return a `DetectionResult` object with a clear confidence score, method, and raw results for downstream processing and debugging.
- **Script & Pattern-Based Detection:** A high-confidence first-pass detector uses Unicode script ranges and word patterns to quickly identify many languages (e.g., `zh`, `ja`, `es`, `pt`, `th`).
- **Configuration:** The entire feature can be managed via configuration, including enabling/disabling the service, selecting backends, and setting confidence thresholds.
- **Enhanced Logging:** Detailed metadata is stored in the processing context for excellent debuggability.

## Future Enhancements

The following enhancements are planned in phases to build upon the current implementation.

### Phase 1: Code Architecture and Specialization

The immediate next step is to refactor the codebase for better scalability and to add more specialized detection logic.

**1. Modular Code Refactoring**
- **Action:** Break down the single `language_detection.py` file into the planned modular architecture.
- **Rationale:** Improve maintainability, testability, and scalability as more features are added.
- **Proposed Structure:**
  ```
  language_detection/
  ├── __init__.py
  ├── step.py                 # Main pipeline step
  ├── backends/
  │   ├── base.py, langdetect.py, langid.py, pycld2.py
  ├── patterns/
  │   ├── repository.py, languages/...
  └── analyzers/
      ├── script.py, confidence.py
  ```

**2. Specialized Language Detectors**
- **Action:** Create dedicated detectors for language families that require more nuanced differentiation.
- **Detectors to Add:**
  - **`CyrillicLanguageDetector`:** Distinguish between Russian (`ru`), Mongolian (`mn`), and Ukrainian (`uk`).
  - **`CJKDetector`:** Improve disambiguation between Chinese (`zh`), Japanese (`ja`), and Korean (`ko`).

### Phase 2: Advanced Processing and Language Coverage

This phase focuses on improving accuracy for difficult cases and expanding the number of supported languages.

**1. Text Preprocessing Pipeline**
- **Action:** Implement an intelligent preprocessing pipeline to improve detection accuracy, especially for short or ambiguous texts.
- **Features:**
  - N-gram extraction
  - Technical content detection (e.g., code snippets)
  - Text variation generation for very short inputs

**2. Extended Language Support**
- **Action:** Add patterns and detection logic for the following languages.
- **Languages to Add:**
  - Vietnamese (`vi`)
  - Turkish (`tr`)
  - Polish (`pl`)
  - Dutch (`nl`)
  - Swedish (`sv`), Norwegian (`no`), Danish (`da`), Finnish (`fi`)
  - Indonesian (`id`), Malay (`ms`)

### Phase 3: Performance and Reliability

The final phase will focus on optimizing the system for speed and ensuring its reliability through comprehensive testing.

**1. Performance Optimizations**
- **Action:** Implement caching and support for batch processing.
- **Benefits:**
  - **Caching:** Avoid re-processing of identical texts, significantly speeding up common interactions.
  - **Batch Processing:** Allow multiple detection requests to be handled in a single, efficient operation.

**2. Comprehensive Testing**
- **Action:** Develop a full test suite with a large, varied dataset.
- **Requirements:**
  - **Unit & Integration Tests:** Cover all backends, detectors, and the ensemble logic.
  - **Test Dataset:** Curate a dataset with 100+ samples per language, including various text lengths and mixed-language examples.
  - **Benchmarking:** Establish performance benchmarks to track detection speed.

## Success Metrics

These metrics will be used to validate the successful implementation of the features in this roadmap.

- **Accuracy**: >95% for major languages, >85% for all supported languages
- **Performance**: <50ms average detection time
- **Coverage**: Support for 50+ languages
- **Reliability**: <0.1% failure rate
