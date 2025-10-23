#!/usr/bin/env python3
"""
Validate Elasticsearch Sample Data

Quick script to verify indexed data and show statistics.

USAGE:
    python utils/elasticsearch-intent-template/validate_data.py [--index INDEX_NAME]

EXAMPLES:
    # Check default index
    python utils/elasticsearch-intent-template/validate_data.py

    # Check specific index
    python utils/elasticsearch-intent-template/validate_data.py --index logs-app-production
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime
import yaml

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")


async def validate_data(index_name: str = "logs-app-demo"):
    """Validate indexed data and show statistics"""
    print(f"🔍 Validating data in index: {index_name}")
    print("=" * 60)

    try:
        # Load config
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Import after path is set
        from datasources.registry import get_registry

        # Get Elasticsearch datasource
        registry = get_registry()
        es_datasource = registry.get_or_create_datasource(
            datasource_name="elasticsearch",
            config={'datasources': config.get('datasources', {})}
        )

        if not es_datasource.is_initialized:
            await es_datasource.initialize()

        es_client = es_datasource.client

        # Check if index exists
        exists = await es_client.indices.exists(index=index_name)
        if not exists:
            print(f"❌ Index '{index_name}' does not exist")
            return

        print(f"✅ Index exists: {index_name}")

        # Get index stats
        stats = await es_client.indices.stats(index=index_name)
        doc_count = stats['indices'][index_name]['total']['docs']['count']
        size_bytes = stats['indices'][index_name]['total']['store']['size_in_bytes']
        size_mb = size_bytes / (1024 * 1024)

        print(f"📊 Total documents: {doc_count:,}")
        print(f"💾 Index size: {size_mb:.2f} MB")
        print()

        # Get log level distribution
        print("📈 Log Level Distribution:")
        agg_response = await es_client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "levels": {
                        "terms": {
                            "field": "level",
                            "size": 10
                        }
                    }
                }
            }
        )

        for bucket in agg_response['aggregations']['levels']['buckets']:
            level = bucket['key']
            count = bucket['doc_count']
            percentage = (count / doc_count) * 100
            print(f"  {level:8s}: {count:6,} ({percentage:5.1f}%)")

        print()

        # Get service distribution
        print("🔧 Service Distribution:")
        agg_response = await es_client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "services": {
                        "terms": {
                            "field": "service_name",
                            "size": 15
                        }
                    }
                }
            }
        )

        for bucket in agg_response['aggregations']['services']['buckets']:
            service = bucket['key']
            count = bucket['doc_count']
            print(f"  {service:25s}: {count:6,}")

        print()

        # Get environment distribution
        print("🌍 Environment Distribution:")
        agg_response = await es_client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "environments": {
                        "terms": {
                            "field": "environment",
                            "size": 5
                        }
                    }
                }
            }
        )

        for bucket in agg_response['aggregations']['environments']['buckets']:
            env = bucket['key']
            count = bucket['doc_count']
            percentage = (count / doc_count) * 100
            print(f"  {env:12s}: {count:6,} ({percentage:5.1f}%)")

        print()

        # Show time range
        print("📅 Time Range:")
        time_response = await es_client.search(
            index=index_name,
            body={
                "size": 0,
                "aggs": {
                    "min_time": {"min": {"field": "timestamp"}},
                    "max_time": {"max": {"field": "timestamp"}}
                }
            }
        )

        min_ts = time_response['aggregations']['min_time']['value']
        max_ts = time_response['aggregations']['max_time']['value']

        if min_ts and max_ts:
            min_date = datetime.fromtimestamp(min_ts / 1000)
            max_date = datetime.fromtimestamp(max_ts / 1000)
            days_span = (max_date - min_date).days

            print(f"  Earliest: {min_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Latest:   {max_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Span:     {days_span} days")

        print()

        # Sample recent documents
        print("📝 Sample Recent Documents (3):")
        sample_response = await es_client.search(
            index=index_name,
            body={
                "size": 3,
                "sort": [{"timestamp": {"order": "desc"}}],
                "_source": ["timestamp", "level", "service_name", "message"]
            }
        )

        for i, hit in enumerate(sample_response['hits']['hits'], 1):
            source = hit['_source']
            print(f"\n  {i}. [{source['level']}] {source['service_name']}")
            print(f"     {source['timestamp']}")
            print(f"     {source['message'][:80]}{'...' if len(source['message']) > 80 else ''}")

        print()
        print("=" * 60)
        print("✅ Validation complete!")

        # Cleanup
        await es_datasource.close()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description='Validate Elasticsearch sample data')
    parser.add_argument('--index', default='logs-app-demo',
                       help='Elasticsearch index name to validate')

    args = parser.parse_args()

    await validate_data(args.index)


if __name__ == '__main__':
    asyncio.run(main())
