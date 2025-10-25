# Firecrawl Knowledge Retrieval Test Queries

This document contains example queries to test the Firecrawl knowledge retrieval adapter. The adapter treats authoritative web sources (Wikipedia, official documentation) as an online database, mapping natural language questions about topics to specific URLs for content extraction.

## Technology & Programming Topics

### Web Scraping
- **Query**: "Tell me about web scraping"
- **Expected Topic**: web scraping
- **Matching Template**: `find_information_web_scraping`
- **Source URL**: https://en.wikipedia.org/wiki/Web_scraping
- **Expected Behavior**: Retrieve and extract comprehensive information about web scraping from Wikipedia

- **Query**: "What is web scraping?"
- **Expected Topic**: web scraping
- **Matching Template**: `find_information_web_scraping`
- **Expected Behavior**: Return encyclopedic overview of web scraping techniques

- **Query**: "Explain web scraping to me"
- **Expected Topic**: web scraping
- **Matching Template**: `find_information_web_scraping`
- **Expected Behavior**: Provide detailed explanation from authoritative source

### Machine Learning
- **Query**: "What is machine learning?"
- **Expected Topic**: machine learning
- **Matching Template**: `find_information_machine_learning`
- **Source URL**: https://en.wikipedia.org/wiki/Machine_learning
- **Expected Behavior**: Retrieve comprehensive machine learning information

- **Query**: "Tell me about machine learning"
- **Expected Topic**: machine learning
- **Matching Template**: `find_information_machine_learning`
- **Expected Behavior**: Return ML concepts, algorithms, and applications

- **Query**: "I need info on machine learning"
- **Expected Topic**: machine learning
- **Matching Template**: `find_information_machine_learning`
- **Expected Behavior**: Fetch ML overview from Wikipedia

### Python Programming
- **Query**: "Tell me about Python programming"
- **Expected Topic**: Python
- **Matching Template**: `find_information_python`
- **Source URL**: https://en.wikipedia.org/wiki/Python_(programming_language)
- **Expected Behavior**: Retrieve Python programming language information

- **Query**: "What is Python?"
- **Expected Topic**: Python
- **Matching Template**: `find_information_python`
- **Expected Behavior**: Return Python language overview and features

- **Query**: "Python programming overview"
- **Expected Topic**: Python
- **Matching Template**: `find_information_python`
- **Expected Behavior**: Provide comprehensive Python information

### Artificial Intelligence
- **Query**: "What is artificial intelligence?"
- **Expected Topic**: artificial intelligence
- **Matching Template**: `find_information_artificial_intelligence`
- **Source URL**: https://en.wikipedia.org/wiki/Artificial_intelligence
- **Expected Behavior**: Retrieve AI information from Wikipedia

- **Query**: "Tell me about AI"
- **Expected Topic**: AI
- **Matching Template**: `find_information_artificial_intelligence`
- **Expected Behavior**: Return comprehensive AI overview

- **Query**: "Explain artificial intelligence"
- **Expected Topic**: artificial intelligence
- **Matching Template**: `find_information_artificial_intelligence`
- **Expected Behavior**: Provide detailed AI explanation

## Science Topics

### Climate Change
- **Query**: "Tell me about climate change"
- **Expected Topic**: climate change
- **Matching Template**: `find_information_climate_change`
- **Source URL**: https://en.wikipedia.org/wiki/Climate_change
- **Expected Behavior**: Retrieve climate change information

- **Query**: "What is climate change?"
- **Expected Topic**: climate change
- **Matching Template**: `find_information_climate_change`
- **Expected Behavior**: Return scientific overview of climate change

- **Query**: "Explain global warming"
- **Expected Topic**: global warming / climate change
- **Matching Template**: `find_information_climate_change`
- **Expected Behavior**: Provide climate change and global warming details

### Quantum Computing
- **Query**: "What is quantum computing?"
- **Expected Topic**: quantum computing
- **Matching Template**: `find_information_quantum_computing`
- **Source URL**: https://en.wikipedia.org/wiki/Quantum_computing
- **Expected Behavior**: Retrieve quantum computing information

- **Query**: "Tell me about quantum computers"
- **Expected Topic**: quantum computers
- **Matching Template**: `find_information_quantum_computing`
- **Expected Behavior**: Return quantum computing overview

- **Query**: "How do quantum computers work?"
- **Expected Topic**: quantum computers
- **Matching Template**: `find_information_quantum_computing`
- **Expected Behavior**: Explain quantum computing principles

## Documentation Retrieval

### Python Documentation
- **Query**: "I need Python documentation"
- **Expected Topic**: Python documentation
- **Matching Template**: `find_python_documentation`
- **Source URL**: https://docs.python.org/3/
- **Expected Behavior**: Retrieve official Python documentation

- **Query**: "Show me Python docs"
- **Expected Topic**: Python docs
- **Matching Template**: `find_python_documentation`
- **Expected Behavior**: Return Python official documentation

- **Query**: "Python reference documentation"
- **Expected Topic**: Python documentation
- **Matching Template**: `find_python_documentation`
- **Expected Behavior**: Fetch Python reference materials

### JavaScript MDN Documentation
- **Query**: "I need JavaScript documentation"
- **Expected Topic**: JavaScript documentation
- **Matching Template**: `find_javascript_mdn_docs`
- **Source URL**: https://developer.mozilla.org/en-US/docs/Web/JavaScript
- **Expected Behavior**: Retrieve JavaScript MDN documentation

- **Query**: "Show me JavaScript docs"
- **Expected Topic**: JavaScript docs
- **Matching Template**: `find_javascript_mdn_docs`
- **Expected Behavior**: Return MDN JavaScript reference

- **Query**: "MDN JavaScript docs"
- **Expected Topic**: JavaScript MDN
- **Matching Template**: `find_javascript_mdn_docs`
- **Expected Behavior**: Fetch JavaScript documentation from MDN

## Business & Technology

### Blockchain
- **Query**: "What is blockchain?"
- **Expected Topic**: blockchain
- **Matching Template**: `find_information_blockchain`
- **Source URL**: https://en.wikipedia.org/wiki/Blockchain
- **Expected Behavior**: Retrieve blockchain technology information

- **Query**: "Tell me about blockchain"
- **Expected Topic**: blockchain
- **Matching Template**: `find_information_blockchain`
- **Expected Behavior**: Return blockchain overview and concepts

- **Query**: "Explain blockchain technology"
- **Expected Topic**: blockchain technology
- **Matching Template**: `find_information_blockchain`
- **Expected Behavior**: Provide detailed blockchain explanation

### Cryptocurrency
- **Query**: "What is cryptocurrency?"
- **Expected Topic**: cryptocurrency
- **Matching Template**: `find_information_cryptocurrency`
- **Source URL**: https://en.wikipedia.org/wiki/Cryptocurrency
- **Expected Behavior**: Retrieve cryptocurrency information

- **Query**: "Tell me about cryptocurrency"
- **Expected Topic**: cryptocurrency
- **Matching Template**: `find_information_cryptocurrency`
- **Expected Behavior**: Return crypto overview and concepts

- **Query**: "I need info on crypto"
- **Expected Topic**: crypto
- **Matching Template**: `find_information_cryptocurrency`
- **Expected Behavior**: Provide cryptocurrency details

## Expected Response Format

Each successful query should return a context document with structured knowledge from the mapped source:

```json
{
  "content": "Successfully scraped content from: https://en.wikipedia.org/wiki/Web_scraping\n\nPage Information:\nTitle: Web scraping - Wikipedia\nDescription: Web scraping overview\nLanguage: en\n\nMarkdown Content:\n[Full Wikipedia article content in markdown format...]",
  "metadata": {
    "source": "firecrawl",
    "template_id": "find_information_web_scraping",
    "query_intent": "Find information about web scraping techniques and concepts",
    "parameters_used": {},
    "similarity": 0.92,
    "result_count": 1,
    "scraped_url": "https://en.wikipedia.org/wiki/Web_scraping",
    "scrape_success": true,
    "page_metadata": {
      "title": "Web scraping - Wikipedia",
      "description": "Web scraping overview",
      "language": "en"
    },
    "results": [
      {
        "url": "https://en.wikipedia.org/wiki/Web_scraping",
        "success": true,
        "markdown": "[content...]",
        "metadata": {
          "title": "Web scraping - Wikipedia",
          "description": "Web scraping overview",
          "language": "en"
        }
      }
    ]
  },
  "confidence": 0.92
}
```

## Knowledge Retrieval Patterns

This adapter operates differently from traditional web scrapers:

1. **Topic-Based Mapping**: Natural language questions about topics are mapped to authoritative URLs
2. **Curated Sources**: Only predefined, trusted sources (Wikipedia, official docs) are accessed
3. **No Arbitrary URLs**: Unlike generic scrapers, this treats web sources as a structured knowledge database
4. **Consistent Quality**: All sources are vetted for reliability and authority

## Adding New Knowledge Topics

To add new topics to the knowledge base:

1. Identify authoritative source URL
2. Add template to `firecrawl_templates.yaml` with hardcoded URL mapping
3. Define natural language examples for the topic
4. Test with queries in this document
5. Verify content extraction quality

## Error Cases

### Unknown Topics
- **Query**: "Tell me about quantum entanglement teleportation"
- **Expected Behavior**: No matching template found, low confidence score

### Ambiguous Topics
- **Query**: "What is Java?"
- **Expected Behavior**: May match multiple contexts (programming language, island, coffee)

### Network/API Errors
- **Expected Behavior**: Graceful error handling with informative messages about scraping failures

## Performance Considerations

### Large Content Handling
Wikipedia articles and documentation pages can be very large (50KB+):
- **Current**: Full content returned in single response
- **Recommendation**: Implement chunking for content > 10KB
- **Future Enhancement**: Use Redis cache to store chunked content with expiry
