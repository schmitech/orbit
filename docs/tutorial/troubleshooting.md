# Troubleshooting

| Symptom | Try this |
|:---|:---|
| `curl /health` hangs or refuses | Server isn't running — check `./bin/orbit.sh start` logs |
| "Adapter … is not available" | The adapter is disabled in `config/adapters/*.yaml`, or was toggled off in the admin panel. Toggling now applies immediately (2.6.6) |
| 401 or "unauthorized" from OpenAI / other provider | Set the provider's API key env var (e.g. `OPENAI_API_KEY`) before `./bin/orbit.sh start` |
| "No matching template found" | Lower `confidence_threshold`, or add more `nl_examples` to your template YAML |
| Slow template matching | Make sure your embedding provider is reachable; check logs for `Preloading embedding provider…` |
| File upload fails | Check `max_file_size` in the multimodal adapter and supported types above |
| Intent SQL returns wrong year / param | Explicit years should bind correctly on recent versions — double-check the template's parameter names |
| Vector QA returns "I don't have information about that" | Threshold may be too strict; drop `confidence_threshold` by 0.05–0.1 |

Logs live in `logs/orbit.log`. The admin panel's audit view (2.6.6) surfaces adapter toggles, config edits, and auth events.

---

[Tutorial home](../tutorial.md) | [Previous: Adapter Configuration Reference](adapter-configuration-reference.md) | [Next: Next Steps](next-steps.md)

---
