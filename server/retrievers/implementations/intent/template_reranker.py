"""
Template reranking system for Intent retriever using domain-specific rules
"""

import logging
from typing import Any, Dict, List

from .domain import DomainConfig
from .domain_strategies.registry import DomainStrategyRegistry

logger = logging.getLogger(__name__)


class TemplateReranker:
    """Rerank templates using domain-specific rules and vocabulary"""
    
    def __init__(self, domain_config: Any):
        if isinstance(domain_config, DomainConfig):
            self.domain_config = domain_config
        else:
            self.domain_config = DomainConfig(domain_config or {})

        self.domain_name = self.domain_config.domain_name.lower()

        self.domain_strategy = DomainStrategyRegistry.get_strategy(
            self.domain_config.domain_name,
            self.domain_config,
        )
        if not self.domain_strategy and self.domain_name:
            logger.info(
                "No specific strategy for domain '%s', using generic reranking only",
                self.domain_name,
            )
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]:
        """Rerank templates using domain-specific rules and generic rules"""
        query_lower = user_query.lower()
        
        for template_info in templates:
            template = template_info['template']
            boost = 0.0
            
            # Apply domain-specific boosting if available
            if self.domain_strategy:
                boost += self.domain_strategy.calculate_domain_boost(
                    template_info, user_query, self.domain_config
                )
            
            # Apply generic boosting rules
            boost += self._calculate_generic_boost(template, query_lower)
            
            # Apply boost
            original_similarity = template_info['similarity']
            template_info['similarity'] = min(1.0, original_similarity + boost)
            template_info['boost_applied'] = boost
            
            if boost > 0:
                logger.debug(f"Template {template.get('id')} boosted by {boost:.3f} "
                           f"(original: {original_similarity:.3f}, new: {template_info['similarity']:.3f})")
        
        # Re-sort by adjusted similarity
        return sorted(templates, key=lambda x: x['similarity'], reverse=True)
    
    def _calculate_generic_boost(self, template: Dict, query_lower: str) -> float:
        """Calculate boost using generic rules applicable to any domain"""
        boost = 0.0
        
        # Check semantic tags
        semantic_tags = template.get('semantic_tags', {})
        if semantic_tags:
            # Entity matching
            primary_entity = semantic_tags.get('primary_entity')
            if primary_entity:
                boost += self._calculate_entity_boost(query_lower, primary_entity)
            
            # Action matching
            action = semantic_tags.get('action')
            if action:
                boost += self._calculate_action_boost(query_lower, action)
            
            # Qualifier matching
            qualifiers = semantic_tags.get('qualifiers', [])
            for qualifier in qualifiers:
                if qualifier.lower() in query_lower:
                    boost += 0.1
        
        # Tag matching
        tags = template.get('tags', [])
        for tag in tags:
            if tag.lower() in query_lower:
                boost += 0.05
        
        # Natural language example matching
        nl_examples = template.get('nl_examples', [])
        for example in nl_examples:
            similarity = self._calculate_text_similarity(query_lower, example.lower())
            if similarity > 0.5:
                boost += similarity * 0.2
        
        return boost
    
    def _calculate_entity_boost(self, query_lower: str, primary_entity: str) -> float:
        """Calculate boost for entity matches"""
        boost = 0.0
        # Check primary entity name
        if primary_entity.lower() in query_lower:
            boost += 0.2
        
        # Check entity synonyms
        synonyms = self.domain_config.get_entity_synonyms(primary_entity)
        for synonym in synonyms:
            if synonym.lower() in query_lower:
                boost += 0.15
                break  # Don't double count
        
        return boost
    
    def _calculate_action_boost(self, query_lower: str, action: str) -> float:
        """Calculate boost for action verb matches"""
        boost = 0.0
        action_verbs = self.domain_config.vocabulary.get('action_verbs', {})
        
        # Check if action or its synonyms are in query
        verbs = action_verbs.get(action, [])
        verbs.append(action)  # Include the action itself
        
        for verb in verbs:
            if verb.lower() in query_lower:
                boost += 0.15
                break  # Don't double count
        
        return boost
    
    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity between two strings"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def explain_ranking(self, templates: List[Dict]) -> str:
        """Generate explanation of template ranking for debugging"""
        lines = ["Template Ranking Explanation:", "=" * 30]
        
        for i, template_info in enumerate(templates[:5]):  # Top 5
            template = template_info['template']
            similarity = template_info['similarity']
            boost = template_info.get('boost_applied', 0.0)
            original = similarity - boost
            
            lines.append(f"{i+1}. {template.get('id', 'Unknown')} (similarity: {similarity:.3f})")
            lines.append(f"   Original: {original:.3f}, Boost: +{boost:.3f}")
            lines.append(f"   Description: {template.get('description', 'N/A')}")
            
            semantic_tags = template.get('semantic_tags', {})
            if semantic_tags:
                lines.append(f"   Entity: {semantic_tags.get('primary_entity', 'N/A')}")
                lines.append(f"   Action: {semantic_tags.get('action', 'N/A')}")
            
            if self.domain_strategy and self.domain_name:
                lines.append(f"   Domain Strategy: {self.domain_strategy.__class__.__name__}")
            
            lines.append("")
        
        return "\n".join(lines)
