// Ticket deck with ground-truth labels. The game scores both lanes against `team`;
// `urgency` is shown next to the AI's answer for context. A few tickets are deliberately
// borderline so the model's confidence varies on screen.
export const TEAMS = [
  { id: "billing", label: "Billing", key: "1" },
  { id: "technical", label: "Technical", key: "2" },
  { id: "account", label: "Account", key: "3" },
  { id: "other", label: "Other", key: "4" },
];

// A second deck asks where the next scarce support slot should go. The policy is
// deliberately short enough to stay visible while tickets fall.
export const RESOURCE_OPTIONS = [
  { id: "dispatch", label: "Dispatch", key: "1" },
  { id: "escalate", label: "Escalate", key: "2" },
  { id: "queue", label: "Queue", key: "3" },
  { id: "self_serve", label: "Self-serve", key: "4" },
];

export const RESOURCE_POLICY = "Critical = active outage, security exposure, or data loss. Dispatch critical work when the needed specialist is free; otherwise escalate for backup. Queue a blocked noncritical workflow. Send information and how-to requests to self-serve. Customer tier and angry wording do not override impact.";

export const RESOURCE_QUESTION = {
  action: {
    type: "choice",
    instructions: "Apply the resource policy to this case. What is the next action?",
    criteria: {
      dispatch: "Critical incident and the required specialist is available now",
      escalate: "Critical incident but the required specialist is unavailable; seek backup",
      queue: "Noncritical work is blocked and needs a specialist later",
      self_serve: "Information or how-to request; no specialist intervention needed",
    },
  },
};

export const RESOURCE_TICKETS = [
  { answer: "dispatch", resource: "Security · 1 free", text: "A former admin is exporting customer records right now. Our security specialist is free." },
  { answer: "escalate", resource: "Security · 0 free", text: "A former admin is exporting customer records right now. Security is occupied on another incident." },
  { answer: "dispatch", resource: "Platform · 1 free", text: "Every customer checkout is returning 500 errors. One platform engineer can take this now." },
  { answer: "escalate", resource: "Platform · 0 free", text: "Every customer checkout is returning 500 errors. All platform engineers are already committed." },
  { answer: "dispatch", resource: "Data · 1 free", text: "The sync is deleting live customer records. A data specialist is available now." },
  { answer: "escalate", resource: "Data · 0 free", text: "The sync is deleting live customer records. The data team has no free specialist." },
  { answer: "queue", resource: "Billing · 0 free", text: "Month-end is next week. An error blocks our invoice export; billing support is at capacity." },
  { answer: "queue", resource: "Account · 1 free", text: "An owner can still administer the workspace, but one teammate cannot reset their password." },
  { answer: "queue", resource: "Platform · 1 free", text: "Customer-facing dashboards work. Our internal report has been stuck since yesterday." },
  { answer: "queue", resource: "Billing · 1 free", text: "Our enterprise discount was missed on this month's invoice. Finance needs it corrected this week." },
  { answer: "self_serve", resource: "Platform · 0 free", text: "No requests are failing. What is the documented API rate limit for next quarter?" },
  { answer: "self_serve", resource: "Billing · 0 free", text: "The billing page opens. Where can I download last month's invoice?" },
  { answer: "self_serve", resource: "Account · 1 free", text: "Nothing is broken. How do I invite a teammate with read-only access?" },
  { answer: "queue", resource: "Platform · 0 free", text: "The rest of the dashboard works. Our CEO says one blank optional chart is urgent." },
  { answer: "escalate", resource: "Security · 0 free", text: "An exposed API key is being used from an unknown IP. The security specialist is unavailable." },
  { answer: "dispatch", resource: "Platform · 1 free", text: "Our payment integration is down for all buyers. The platform engineer just became available." },
];

export const TICKETS = [
  // Billing
  { team: "billing", urgency: "Soon", text: "I was charged twice for my subscription this month. Please refund the duplicate payment." },
  { team: "billing", urgency: "Routine", text: "Can I get a copy of last month's invoice as a PDF for my accountant?" },
  { team: "billing", urgency: "Soon", text: "My card was declined at renewal but the money still left my bank account." },
  { team: "billing", urgency: "Routine", text: "How do I switch from monthly to annual billing to get the discount?" },
  { team: "billing", urgency: "Urgent", text: "You charged our company card $4,800 instead of $480. Reverse this today." },
  { team: "billing", urgency: "Routine", text: "Please add our VAT number to future invoices." },
  { team: "billing", urgency: "Soon", text: "I cancelled last week but was still billed for another month. I want my money back." },
  { team: "billing", urgency: "Routine", text: "Do you accept payment by bank transfer instead of credit card?" },
  { team: "billing", urgency: "Routine", text: "The price on my receipt doesn't match the price on your pricing page." },
  { team: "billing", urgency: "Soon", text: "I got a refund notice but the money never showed up on my statement." },
  { team: "billing", urgency: "Routine", text: "Can I update the billing address that appears on my invoices?" },
  { team: "billing", urgency: "Soon", text: "Why was I charged a late fee? I paid on the due date." },
  { team: "billing", urgency: "Routine", text: "Is there a nonprofit discount on the team plan?" },
  { team: "billing", urgency: "Soon", text: "The free trial converted to paid without any warning. Please refund it." },
  { team: "billing", urgency: "Routine", text: "Our finance team needs invoices sent to a different email address." },
  { team: "billing", urgency: "Urgent", text: "Unknown charges from you keep appearing on my card every hour. Stop them now." },
  { team: "billing", urgency: "Routine", text: "What currency will I be billed in if I'm based in Canada?" },
  { team: "billing", urgency: "Soon", text: "I downgraded my plan but I'm still paying the old higher price." },
  { team: "billing", urgency: "Routine", text: "Can you split our invoice across two cost centers?" },
  { team: "billing", urgency: "Soon", text: "Coupon code SPRING20 was accepted but no discount was applied to my bill." },

  // Technical
  { team: "technical", urgency: "Urgent", text: "Your API returns 500 errors on every POST request since this morning." },
  { team: "technical", urgency: "Soon", text: "The mobile app crashes as soon as I open the camera screen." },
  { team: "technical", urgency: "Routine", text: "CSV export puts all the data in one column in Excel." },
  { team: "technical", urgency: "Urgent", text: "The whole dashboard is down for everyone in our office. Nothing loads." },
  { team: "technical", urgency: "Soon", text: "Webhooks stopped firing after we rotated our signing secret." },
  { team: "technical", urgency: "Routine", text: "Dark mode makes the chart labels impossible to read." },
  { team: "technical", urgency: "Soon", text: "Search results take over 30 seconds to load since the last update." },
  { team: "technical", urgency: "Routine", text: "How do I connect your service to our Slack workspace?" },
  { team: "technical", urgency: "Urgent", text: "Data sync is deleting records in our CRM. Please help immediately." },
  { team: "technical", urgency: "Soon", text: "File uploads over 10 MB fail with a timeout error." },
  { team: "technical", urgency: "Routine", text: "The date picker shows the wrong week start for our region." },
  { team: "technical", urgency: "Soon", text: "Push notifications stopped arriving on Android after the update." },
  { team: "technical", urgency: "Routine", text: "Is there a rate limit on the reporting API? We keep getting 429s." },
  { team: "technical", urgency: "Soon", text: "Our Zapier integration shows 'invalid token' on every run." },
  { team: "technical", urgency: "Routine", text: "The page layout breaks when I zoom the browser to 150%." },
  { team: "technical", urgency: "Urgent", text: "Checkout on our store widget is broken and customers can't pay us." },
  { team: "technical", urgency: "Routine", text: "Emails from your system are landing in our spam folder." },
  { team: "technical", urgency: "Soon", text: "The desktop app won't start on the latest macOS. It just bounces and quits." },
  { team: "technical", urgency: "Routine", text: "Your SDK throws a deprecation warning on Python 3.12." },
  { team: "technical", urgency: "Soon", text: "Reports show yesterday's numbers even after I refresh." },

  // Account
  { team: "account", urgency: "Soon", text: "I forgot my password and the reset email never arrives." },
  { team: "account", urgency: "Routine", text: "How do I change the email address on my profile?" },
  { team: "account", urgency: "Urgent", text: "Someone logged into my account from another country. Lock it now." },
  { team: "account", urgency: "Soon", text: "I lost my phone and can't get past two-factor authentication." },
  { team: "account", urgency: "Routine", text: "Please delete my account and all my personal data." },
  { team: "account", urgency: "Routine", text: "How do I add a new teammate to our workspace?" },
  { team: "account", urgency: "Soon", text: "My account is locked after too many login attempts." },
  { team: "account", urgency: "Routine", text: "I want to change my username." },
  { team: "account", urgency: "Routine", text: "Can I transfer ownership of the workspace to my colleague?" },
  { team: "account", urgency: "Soon", text: "Single sign-on with Google keeps sending me back to the login page." },
  { team: "account", urgency: "Routine", text: "How do I turn off the marketing emails in my profile settings?" },
  { team: "account", urgency: "Urgent", text: "A former employee still has admin access to our account. Remove them now." },
  { team: "account", urgency: "Routine", text: "I'd like to merge my two accounts into one." },
  { team: "account", urgency: "Soon", text: "The verification code you text me is always expired by the time it arrives." },
  { team: "account", urgency: "Routine", text: "Where do I update my display name and profile photo?" },
  { team: "account", urgency: "Soon", text: "I changed my password but I'm still logged in on an old laptop. Sign it out." },
  { team: "account", urgency: "Routine", text: "Can I set a different time zone for my profile?" },
  { team: "account", urgency: "Routine", text: "How do I give a teammate read-only permissions?" },
  { team: "account", urgency: "Soon", text: "My invitation link says it has expired. Can you resend it?" },
  { team: "account", urgency: "Routine", text: "I want to download a copy of all my account data." },

  // Other
  { team: "other", urgency: "Routine", text: "Do you have any job openings for designers?" },
  { team: "other", urgency: "Routine", text: "I'd love to see a feature that lets me schedule reports weekly." },
  { team: "other", urgency: "Routine", text: "Just wanted to say your support team was fantastic last week. Thanks!" },
  { team: "other", urgency: "Routine", text: "Can I get a sticker pack for our office?" },
  { team: "other", urgency: "Routine", text: "Are you going to be at the trade show in Toronto next month?" },
  { team: "other", urgency: "Routine", text: "I'm a journalist writing about AI startups. Who handles press inquiries?" },
  { team: "other", urgency: "Routine", text: "Do you offer a partner or reseller program?" },
  { team: "other", urgency: "Routine", text: "What's the story behind your company name?" },
  { team: "other", urgency: "Routine", text: "Could you recommend a good book on customer success?" },
  { team: "other", urgency: "Routine", text: "Is your office open to visitors? I'm in town on Friday." },
  { team: "other", urgency: "Routine", text: "Please add a French version of your website." },
  { team: "other", urgency: "Routine", text: "I'm a student and would like to interview someone on your team for a project." },

  // Borderline: a wrong answer here is understandable, and the confidence bar should show it.
  { team: "billing", urgency: "Soon", text: "I can't log in to download my invoice and my payment is due tomorrow." },
  { team: "technical", urgency: "Soon", text: "The billing page throws an error when I try to open it." },
  { team: "account", urgency: "Routine", text: "I need to change who receives the account notifications, including receipts." },
  { team: "technical", urgency: "Urgent", text: "Login is broken for all our users. The server returns a blank page." },
  { team: "billing", urgency: "Routine", text: "Before I upgrade, can you tell me what the enterprise plan costs?" },
  { team: "other", urgency: "Routine", text: "Your competitor offers a free tier. Will you ever have one?" },
  { team: "account", urgency: "Soon", text: "My company email changed after a merger and I can't access my profile." },
  { team: "technical", urgency: "Routine", text: "The password field doesn't let me paste from my password manager." },
];
