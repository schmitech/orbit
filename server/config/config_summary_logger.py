"""
Diagnostic logging for loaded configuration.
"""

from typing import Any, Dict


def log_config_summary(config: Dict[str, Any], source_path: str, logger) -> None:
    """Log a summary of important config values with sensitive data masked."""
    logger.info(f"Configuration loaded from: {source_path}")

    inference_provider = config.get('general', {}).get('inference_provider', 'ollama')
    provider_config = config.get('inference', {}).get(inference_provider, {})

    if provider_config:
        details = [f"model={provider_config.get('model')}"]
        if provider_config.get('base_url'):
            details.append(f"base_url={mask_url(provider_config.get('base_url'))}")
        logger.info(f"Inference: {inference_provider} - {', '.join(details)}")
    else:
        logger.info(f"Inference: {inference_provider}")

    lang_detect_config = config.get('language_detection', {})
    language_detection = lang_detect_config.get('enabled', False)
    logger.info(f"Language Detection: enabled={language_detection}")

    fault_tolerance_config = config.get('fault_tolerance', {})
    circuit_breaker_config = fault_tolerance_config.get('circuit_breaker', {})
    execution_config = fault_tolerance_config.get('execution', {})
    logger.info(
        f"Fault Tolerance: enabled - strategy={execution_config.get('strategy', 'all')}, "
        f"circuit_breaker_threshold={circuit_breaker_config.get('failure_threshold', 5)}, "
        f"timeout={execution_config.get('timeout', 35)}s"
    )

    perf_config = config.get('performance', {})
    if perf_config:
        workers = perf_config.get('workers', 1)
        keep_alive = perf_config.get('keep_alive_timeout', 30)
        thread_pools = perf_config.get('thread_pools', {})
        if thread_pools:
            total_workers = sum(thread_pools.values())
            pool_summary = ', '.join(
                [f"{k.replace('_workers', '')}={v}" for k, v in thread_pools.items()]
            )
            logger.info(
                f"Performance: workers={workers}, keep_alive={keep_alive}s, "
                f"thread_pools=({pool_summary}), total_capacity={total_workers}"
            )
        else:
            logger.info(
                f"Performance: workers={workers}, keep_alive={keep_alive}s, thread_pools=default"
            )
    else:
        logger.info("Performance: using default configuration")

    adapters_config = config.get('adapters', [])
    if adapters_config:
        enabled_adapters = [adapter for adapter in adapters_config if adapter.get('enabled', True)]
        disabled_adapters = [adapter for adapter in adapters_config if not adapter.get('enabled', True)]
        logger.info(f"Adapters: {len(enabled_adapters)} enabled, {len(disabled_adapters)} disabled")
        if disabled_adapters:
            disabled_names = [adapter.get('name', 'unnamed') for adapter in disabled_adapters]
            logger.info(f"Disabled adapters: {', '.join(disabled_names)}")

    monitoring_config = config.get('monitoring', {})
    if monitoring_config:
        monitoring_enabled = monitoring_config.get('enabled', True)
        metrics_config = monitoring_config.get('metrics', {})

        if monitoring_enabled:
            collection_interval = metrics_config.get('collection_interval', 5)
            time_window = metrics_config.get('time_window', 300)
            prometheus_enabled = metrics_config.get('prometheus', {}).get('enabled', True)
            dashboard_enabled = metrics_config.get('dashboard', {}).get('enabled', True)
            websocket_interval = metrics_config.get('dashboard', {}).get('websocket_update_interval', 5)

            features = []
            if prometheus_enabled:
                features.append("prometheus")
            if dashboard_enabled:
                features.append("dashboard")

            logger.info(
                f"Monitoring: enabled - features=({', '.join(features)}), "
                f"collection_interval={collection_interval}s, time_window={time_window}s, "
                f"websocket_update={websocket_interval}s"
            )

            alerts_config = monitoring_config.get('alerts', {})
            if alerts_config:
                thresholds = []
                if 'cpu_threshold' in alerts_config:
                    thresholds.append(f"cpu={alerts_config['cpu_threshold']}%")
                if 'memory_threshold' in alerts_config:
                    thresholds.append(f"memory={alerts_config['memory_threshold']}%")
                if 'error_rate_threshold' in alerts_config:
                    thresholds.append(f"error_rate={alerts_config['error_rate_threshold']}%")
                if 'response_time_threshold' in alerts_config:
                    thresholds.append(f"response_time={alerts_config['response_time_threshold']}ms")

                if thresholds:
                    logger.info(f"Monitoring Alert Thresholds: {', '.join(thresholds)}")
        else:
            logger.info("Monitoring: disabled")
    else:
        logger.info("Monitoring: using default settings")


def mask_url(url: str) -> str:
    """Mask sensitive parts of URLs like credentials and token query params."""
    if not url:
        return url

    try:
        if '@' in url and '//' in url:
            protocol, rest = url.split('//', 1)
            if '@' in rest:
                _, host_part = rest.split('@', 1)
                return f"{protocol}//[REDACTED]@{host_part}"

        if '?' in url and (
            'key=' in url.lower()
            or 'token=' in url.lower()
            or 'api_key=' in url.lower()
            or 'apikey=' in url.lower()
            or 'password=' in url.lower()
        ):
            base_url, query = url.split('?', 1)
            params = query.split('&')
            masked_params = []

            for param in params:
                param_lower = param.lower()
                if (
                    'key=' in param_lower
                    or 'token=' in param_lower
                    or 'api_key=' in param_lower
                    or 'apikey=' in param_lower
                    or 'password=' in param_lower
                ):
                    param_name = param.split('=')[0]
                    masked_params.append(f"{param_name}=[REDACTED]")
                else:
                    masked_params.append(param)

            return f"{base_url}?{'&'.join(masked_params)}"

        return url
    except Exception:
        return url.split('//')[0] + '//[HOST_REDACTED]' if '//' in url else '[URL_REDACTED]'
