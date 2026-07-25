import { faker } from "@faker-js/faker";

const REGIONS = ["North America", "EMEA", "APAC", "LATAM"];
const SEGMENTS = ["SMB", "Mid-Market", "Enterprise"];
const INDUSTRIES = ["Financial Services", "Healthcare", "Manufacturing", "Retail", "Technology"];
const STAGES = ["Qualification", "Discovery", "Proposal", "Negotiation", "Closed Won", "Closed Lost"];
const OWNERS = ["Avery Chen", "Maya Patel", "Noah Brooks", "Sofia Rivera", "Theo Morgan"];

function buildData() {
  faker.seed(4242);
  const customers = Array.from({ length: 36 }, (_, index) => {
    const segment = faker.helpers.arrayElement(SEGMENTS);
    const region = faker.helpers.arrayElement(REGIONS);
    const arr = faker.number.int({
      min: segment === "Enterprise" ? 240000 : segment === "Mid-Market" ? 72000 : 12000,
      max: segment === "Enterprise" ? 1400000 : segment === "Mid-Market" ? 260000 : 85000
    });
    const healthScore = faker.number.int({ min: 38, max: 96 });
    const renewalDays = faker.number.int({ min: 15, max: 330 });
    const purchasedSeats = faker.number.int({ min: 50, max: segment === "Enterprise" ? 5000 : 1000 });
    const assignedSeats = Math.round(purchasedSeats * faker.number.float({ min: 0.4, max: 0.98 }));
    const activeSeats = Math.round(assignedSeats * faker.number.float({ min: 0.35, max: 0.95 }));

    return {
      id: `cus_${String(index + 1).padStart(4, "0")}`,
      name: faker.company.name(),
      industry: faker.helpers.arrayElement(INDUSTRIES),
      region,
      segment,
      owner: faker.helpers.arrayElement(OWNERS),
      annualRecurringRevenue: arr,
      healthScore,
      renewalDate: faker.date.soon({ days: renewalDays }).toISOString().slice(0, 10),
      purchasedSeats,
      assignedSeats,
      activeSeats,
      openSupportCases: faker.number.int({ min: 0, max: healthScore < 60 ? 12 : 4 }),
      lastExecutiveMeeting: faker.date.recent({ days: 90 }).toISOString().slice(0, 10),
      primaryContact: {
        name: faker.person.fullName(),
        title: faker.person.jobTitle(),
        email: faker.internet.email().toLowerCase()
      },
      riskSignals: faker.helpers.arrayElements(
        [
          "Usage trending down",
          "Procurement review pending",
          "Champion changed roles",
          "Security questionnaire open",
          "Competitive evaluation",
          "Expansion project delayed"
        ],
        faker.number.int({ min: healthScore < 65 ? 2 : 0, max: healthScore < 65 ? 4 : 2 })
      )
    };
  });

  const opportunities = Array.from({ length: 72 }, (_, index) => {
    const customer = faker.helpers.arrayElement(customers);
    const stage = faker.helpers.arrayElement(STAGES);
    const amount = faker.number.int({ min: 15000, max: customer.segment === "Enterprise" ? 850000 : 220000 });
    const probability = {
      Qualification: 15,
      Discovery: 30,
      Proposal: 55,
      Negotiation: 75,
      "Closed Won": 100,
      "Closed Lost": 0
    }[stage];

    return {
      id: `opp_${String(index + 1).padStart(4, "0")}`,
      customerId: customer.id,
      customerName: customer.name,
      name: `${faker.helpers.arrayElement(["Expansion", "Renewal", "Analytics", "Automation", "Platform"])} - ${customer.name}`,
      owner: customer.owner,
      region: customer.region,
      segment: customer.segment,
      stage,
      amount,
      probability,
      weightedAmount: Math.round(amount * probability / 100),
      closeDate: faker.date.soon({ days: 180 }).toISOString().slice(0, 10),
      nextStep: faker.helpers.arrayElement([
        "Confirm business case",
        "Schedule technical validation",
        "Send procurement packet",
        "Align executive sponsors",
        "Review security requirements"
      ])
    };
  });

  const supportTickets = [];
  let ticketIndex = 1;
  for (const customer of customers) {
    const ticketCount = faker.number.int({ min: 1, max: customer.healthScore < 60 ? 6 : 3 });
    for (let i = 0; i < ticketCount; i++) {
      const priority = faker.helpers.weightedArrayElement([
        { weight: 1, value: "P1 - Critical" },
        { weight: 3, value: "P2 - High" },
        { weight: 4, value: "P3 - Medium" },
        { weight: 2, value: "P4 - Low" }
      ]);
      const status = faker.helpers.weightedArrayElement([
        { weight: 4, value: "open" },
        { weight: 1, value: "in_progress" },
        { weight: 5, value: "resolved" }
      ]);
      const slaBreached = priority.startsWith("P1") || priority.startsWith("P2") ? faker.datatype.boolean(0.3) : false;

      supportTickets.push({
        id: `tkt_${String(ticketIndex++).padStart(4, "0")}`,
        customerId: customer.id,
        customerName: customer.name,
        region: customer.region,
        owner: customer.owner,
        priority,
        status,
        subject: faker.hacker.phrase(),
        slaBreached,
        createdAt: faker.date.recent({ days: 30 }).toISOString().slice(0, 10),
        resolutionDays: status === "resolved" ? faker.number.int({ min: 1, max: 7 }) : null
      });
    }
  }

  const salesReps = OWNERS.map((owner) => {
    const repOpportunities = opportunities.filter((o) => o.owner === owner);
    const quota = 1500000;
    const closedWon = repOpportunities
      .filter((o) => o.stage === "Closed Won")
      .reduce((sum, o) => sum + o.amount, 0);
    const activePipeline = repOpportunities
      .filter((o) => !o.stage.startsWith("Closed"))
      .reduce((sum, o) => sum + o.amount, 0);

    return {
      name: owner,
      quota,
      closedWon,
      attainmentPct: Math.round((closedWon / quota) * 100),
      activePipeline,
      dealCount: repOpportunities.length
    };
  });

  return { customers, opportunities, supportTickets, salesReps };
}

export const data = buildData();

export function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(value);
}

export function normalize(value) {
  return String(value ?? "").trim().toLowerCase();
}

