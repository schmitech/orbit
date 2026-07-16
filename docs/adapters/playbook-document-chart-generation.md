# Manual/Integration Check: Document Chart Generation

Use these prompts to verify chart generation in PDF, Word, and PowerPoint documents.
The document renderer supports **bar**, **line**, **area**, and **pie** charts.
Charts are rendered as high-resolution PNGs before being embedded in a document.

Run the prompts through an adapter with the `PDF`, `Word`, or `PowerPoint` skill
available (for example, `simple-chat-with-files`), or use a dedicated generation
adapter.

## 1. Start the server and select a document skill

Start Orbit, then open OrbitChat with an adapter that can invoke document skills.
In the `/` picker, select **PDF**, **Word**, or **PowerPoint** before sending each
prompt. Use a new chat for each scenario so a prior document does not affect the
requested chart.

For API testing, create a key for the appropriate adapter and set `skill` to
`PDF`, `Word`, or `PowerPoint` in the chat request. See [Automatic Skill Intent
Detection](playbook-auto-skill-routing.md) for a full `curl` request example.

## 2. Baseline grouped bar chart

Send:

> Create a short PDF report with a grouped bar chart comparing 2023 revenue
> and operating profit for Apple, Microsoft, Google, Amazon, and Meta.

**Expected:** two clearly distinguished series, a readable legend above the plot,
a concise title, and category labels that do not overlap.

## 3. Long category labels

Send:

> Create a Word report with a bar chart of renewable-energy capacity for
> United States, United Kingdom, United Arab Emirates, South Africa, and New
> Zealand. Use the full country names.

**Expected:** labels wrap onto multiple lines where necessary rather than becoming
steep, cramped diagonal text.

## 4. Line chart with a time sequence

Send:

> Create a PDF with a line chart of monthly website traffic and conversion rate
> from January through December 2025. Include realistic sample data and a short
> analysis below the chart.

**Expected:** each series uses a distinct colored line with visible markers; the
month labels and legend remain readable.

## 5. Area chart with multiple series

Send:

> Create a PowerPoint presentation with a slide containing an area chart of
> quarterly active users for Free, Pro, and Enterprise plans across 2024.

**Expected:** the chart appears on its own slide, using translucent fills and
clear series lines. The slide preserves readable spacing around the chart.

## 6. Pie chart

Send:

> Create a one-page PDF with a pie chart of support-ticket categories:
> Billing 32%, Technical 28%, Account Access 20%, Feature Request 12%, and
> Other 8%.

**Expected:** slices are separated cleanly, labels and percentages are legible,
and the values add up to 100%.

## 7. Compact values and a long title

Send:

> Create a PDF report with a bar chart titled "Top 10 North American Cities by
> 2025 Municipal Clean-Energy Infrastructure Investment". Include ten cities
> and investment values between 1.2 million and 950 million USD.

**Expected:** the title scales to fit, the ten categories remain legible, and large
y-axis values use compact labels such as `1M` and `950M`.

## 8. Multi-series stress test

Send:

> Create a PowerPoint slide with a grouped bar chart comparing Q1, Q2, and Q3
> sales across ten product categories. Use three data series and category names
> longer than ten characters.

**Expected:** all three series appear in the legend, bars remain distinct, and the
chart avoids label and legend collisions.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| The document contains no chart | The generation model did not emit a chart spec. Make the chart type and requested data explicit. |
| The chart has unexpected values | The request did not provide data and the model generated illustrative values. Supply exact numbers when accuracy matters. |
| Text is too small in a presentation | Use the PowerPoint skill; it creates a dedicated chart slide at a larger render size. |
| A `matplotlib.category` informational message appears in logs | Restart after the `matplotlib.category: WARNING` logger setting in `config/config.yaml` is applied. |

## Renderer scope

Charts currently support the `bar`, `line`, `area`, and `pie` types. For data with
incompatible units (for example, revenue in dollars and a percentage rate), prefer
separate charts until a mixed dual-axis type is exposed in the prompt schema.
