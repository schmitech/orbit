// Review/social-post deck for the Sentiment Pulse demo, about one fictional product
// ("Fernlight" — a smart desk lamp). Separate from the eval sets in
// examples/sentiment-pulse/eval/, so the demo can never overfit the gate: this deck's
// labels (`reveal`) are shown only in the optional reveal view, never used to fake
// a live answer — every live answer comes from the adapter through the bridge.
//
// TODO: this is a starter set (~24 reviews) to wire up the dashboard against. Expand
// to the full ~150-review deck described in the eval plan (Phase 2) before using this
// for a real booth demo: mix of short/long posts, a few sarcastic ones, and even
// coverage across all four aspects (price, support, product, delivery).

export const REVIEWS = [
  {
    id: "rev-001",
    text: "Fernlight arrived two days late, but support fixed the billing issue in minutes. Love the lamp itself.",
    reveal: { polarity: "mixed", valence: 3, sarcasm: false, aspects: { price: "not_mentioned", support: "positive", product: "not_mentioned", delivery: "negative" } },
  },
  {
    id: "rev-002",
    text: "Dims perfectly, looks great on my desk, exactly what I wanted.",
    reveal: { polarity: "positive", valence: 4, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "positive", delivery: "not_mentioned" } },
  },
  {
    id: "rev-003",
    text: "Shipment confirmation says it left the warehouse on Tuesday.",
    reveal: { polarity: "neutral", valence: 2, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "not_mentioned", delivery: "not_mentioned" } },
  },
  {
    id: "rev-004",
    text: "Oh great, another firmware update that bricked the touch controls. Fantastic.",
    reveal: { polarity: "negative", valence: 0, sarcasm: true, aspects: { price: "not_mentioned", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-005",
    text: "$60 for a desk lamp is steep, but honestly the build quality justifies it.",
    reveal: { polarity: "mixed", valence: 3, sarcasm: false, aspects: { price: "negative", support: "not_mentioned", product: "positive", delivery: "not_mentioned" } },
  },
  {
    id: "rev-006",
    text: "Cancel my order. Charged me twice and nobody has responded to three emails. I want a manager to call me.",
    reveal: { polarity: "negative", valence: 0, sarcasm: false, aspects: { price: "negative", support: "negative", product: "not_mentioned", delivery: "not_mentioned" } },
  },
  {
    id: "rev-007",
    text: "Pretty disappointed, the hinge already feels loose after a week.",
    reveal: { polarity: "negative", valence: 1, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-008",
    text: "Best desk lamp I've owned, telling everyone I know to get one.",
    reveal: { polarity: "positive", valence: 4, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "positive", delivery: "not_mentioned" } },
  },
  {
    id: "rev-009",
    text: "Box showed up crushed, lamp itself is fine though.",
    reveal: { polarity: "mixed", valence: 2, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "positive", delivery: "negative" } },
  },
  {
    id: "rev-010",
    text: "Does what it says, happy with it so far.",
    reveal: { polarity: "positive", valence: 3, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "positive", delivery: "not_mentioned" } },
  },
  {
    id: "rev-011",
    text: "Lost my saved brightness presets after the last app update. Second time this has happened.",
    reveal: { polarity: "negative", valence: 1, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-012",
    text: "Love how it takes four tries to pair with Bluetooth every single morning.",
    reveal: { polarity: "negative", valence: 1, sarcasm: true, aspects: { price: "not_mentioned", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-013",
    text: "Support walked me through setup over chat, very patient and quick.",
    reveal: { polarity: "positive", valence: 3, sarcasm: false, aspects: { price: "not_mentioned", support: "positive", product: "not_mentioned", delivery: "not_mentioned" } },
  },
  {
    id: "rev-014",
    text: "It's a lamp. It turns on. It turns off.",
    reveal: { polarity: "neutral", valence: 2, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "not_mentioned", delivery: "not_mentioned" } },
  },
  {
    id: "rev-015",
    text: "Arrived a week early, super fast shipping, very impressed.",
    reveal: { polarity: "positive", valence: 3, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "not_mentioned", delivery: "positive" } },
  },
  {
    id: "rev-016",
    text: "Honestly furious. I've needed to charge my phone off this thing for work and the USB port already stopped working.",
    reveal: { polarity: "negative", valence: 0, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-017",
    text: "Good value overall, wish the cord were a bit longer but can't complain much.",
    reveal: { polarity: "positive", valence: 3, sarcasm: false, aspects: { price: "positive", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-018",
    text: "Switching to a competitor. Third time the light has flickered and no one from support has replied.",
    reveal: { polarity: "negative", valence: 0, sarcasm: false, aspects: { price: "not_mentioned", support: "negative", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-019",
    text: "Not bad, not amazing, does the job for the price.",
    reveal: { polarity: "neutral", valence: 2, sarcasm: false, aspects: { price: "positive", support: "not_mentioned", product: "not_mentioned", delivery: "not_mentioned" } },
  },
  {
    id: "rev-020",
    text: "This is genuinely my favorite purchase this year. The dimming curve is perfect.",
    reveal: { polarity: "positive", valence: 4, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "positive", delivery: "not_mentioned" } },
  },
  {
    id: "rev-021",
    text: "Delivery took three weeks with zero tracking updates. Lamp is nice when it finally showed up.",
    reveal: { polarity: "mixed", valence: 2, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "positive", delivery: "negative" } },
  },
  {
    id: "rev-022",
    text: "Love paying full price for a lamp that stopped charging in two weeks. Great investment.",
    reveal: { polarity: "negative", valence: 0, sarcasm: true, aspects: { price: "negative", support: "not_mentioned", product: "negative", delivery: "not_mentioned" } },
  },
  {
    id: "rev-023",
    text: "Solid little lamp, support was quick when I had a question about the warranty.",
    reveal: { polarity: "positive", valence: 3, sarcasm: false, aspects: { price: "not_mentioned", support: "positive", product: "positive", delivery: "not_mentioned" } },
  },
  {
    id: "rev-024",
    text: "I need this account unlocked, I have a deadline tomorrow and can't get back in.",
    reveal: { polarity: "negative", valence: 1, sarcasm: false, aspects: { price: "not_mentioned", support: "not_mentioned", product: "not_mentioned", delivery: "not_mentioned" } },
  },
];
