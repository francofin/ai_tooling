# Institutional Stock Research Agent Specification

## How to Use This Prompt

Replace every bracketed input below, then give the complete specification to the research agent. If an input is unavailable, write `Not specified` and require the agent to make and disclose a reasonable assumption.

---

## Research Assignment

Act as a senior fundamental equity research analyst conducting institutional-quality due diligence on **[COMPANY NAME] ([TICKER], [EXCHANGE])**.

The purpose of this assignment is to understand the company as an operating business—not merely to summarize its financial statements or repeat management's investor-relations materials. Reconstruct how the company creates, delivers, and captures economic value; determine what drives revenue, margins, cash flow, returns on capital, and shareholder value; assess the durability of those drivers; and identify the evidence that would confirm or invalidate the investment thesis.

### Assignment parameters

- Company: **[COMPANY NAME]**
- Ticker and exchange: **[TICKER / EXCHANGE]**
- Primary listing jurisdiction: **[COUNTRY]**
- Research date: **[DATE]**
- Base reporting currency: **[CURRENCY]**
- Historical period: **[DEFAULT: last 5 fiscal years plus latest trailing period]**
- Forecast period: **[DEFAULT: next 3 fiscal years]**
- Relevant benchmark: **[INDEX OR PEER GROUP]**
- Specific questions or concerns: **[OPTIONAL]**
- Available paid databases: **[BLOOMBERG / FACTSET / CAPITAL IQ / ALPHASENSE / TEGUS / PANJIVA / OTHER / NONE]**

## Required Research Standard

1. Conduct original research using current information available as of the research date.
2. Begin with primary sources. Use secondary and alternative sources to expand, verify, or challenge primary disclosures.
3. Cite every material factual claim with a direct link and publication or filing date. Where possible, include a page, section, exhibit, or table reference.
4. Never present an estimate or inference as a disclosed fact.
5. Label important statements as one of:
   - **Reported fact**
   - **Management claim**
   - **Third-party estimate**
   - **Analyst calculation**
   - **Analyst inference**
6. If information is unavailable, state exactly what was searched and what remains unknown. Do not invent customer names, suppliers, market shares, operating metrics, or financial values.
7. Reconcile conflicting figures and explain differences in definitions, periods, currencies, accounting treatments, or geographic classifications.
8. Separate the date an article was published from the date the underlying event occurred.
9. Distinguish the direct customer from the end customer, and distinguish billing location, shipping destination, production location, asset location, and economic exposure.
10. Treat anonymous commentary, reviews, social media, and unsourced aggregators as weak signals, not verified evidence.
11. Avoid false precision. Use ranges and sensitivity analysis when evidence is incomplete.
12. Do not issue a simplistic buy, hold, or sell recommendation. Present evidence, valuation assumptions, scenarios, risks, and decision-relevant conclusions.

## Source Hierarchy

Prioritize sources in this order:

1. Audited financial statements, securities filings, and official regulatory records
2. Legally filed contracts, prospectuses, technical reports, and government databases
3. Disclosures made by customers, suppliers, distributors, and strategic partners
4. Company earnings calls, investor days, presentations, product documentation, and official announcements
5. Competitor filings and industry-association data
6. Reputable industry research and expert interviews
7. Trade publications and high-quality local reporting
8. Alternative data, channel checks, web traffic, shipment data, job postings, product reviews, and pricing observations
9. Anonymous forums, social media, and other unverified commentary

Use the appropriate official filing repository, including SEC EDGAR for U.S. issuers and SEDAR+ for Canadian issuers. Examine the annual filing, latest interim filings, material-event filings, proxy circular, prospectuses, material exhibits, insider filings, beneficial-ownership filings, and relevant subsidiary disclosures.

Search filings for at least the following terms where applicable:

`customer`, `supplier`, `concentration`, `geographic`, `segment`, `backlog`, `bookings`, `capacity`, `utilization`, `contract manufacturer`, `purchase commitment`, `inventory`, `distribution`, `channel`, `raw material`, `pricing`, `renewal`, `retention`, `churn`, `warranty`, `seasonality`, `related party`, `restructuring`, `impairment`, `covenant`, `contingency`, and `cybersecurity`.

## Analytical Tasks

### 1. Executive investment summary

Provide a concise decision-oriented overview covering:

- What the company does and how it makes money
- The two to four variables that most strongly determine its economic results
- The principal source of competitive advantage, if any
- The strongest evidence supporting the business quality
- The largest unresolved question
- The main upside and downside mechanisms
- What expectations appear embedded in the current valuation

Do not write this section until the underlying research is complete.

### 2. Company structure and history

Establish:

- Founding, major strategic transitions, and current corporate structure
- Material subsidiaries, joint ventures, variable-interest entities, and minority interests
- Major acquisitions, divestitures, discontinued operations, and restructurings
- Reporting segments versus the economically useful business divisions
- The relationship between the legal entity, operating entities, and listed security
- Any dual-class shares, controlling shareholders, cross-holdings, or unusual governance arrangements

Create a timeline of events that materially changed the company's revenue mix, asset base, competitive position, capital structure, or share count.

### 3. Business model and value chain

Explain in plain language:

- What the company sells
- The problem its product or service solves
- Who purchases it and who ultimately uses it
- How customers discover, evaluate, purchase, implement, and renew or replace it
- How the company prices and bills
- Whether revenue is recurring, transactional, usage-based, contractual, regulated, or cyclical
- Which activities the company performs internally and which it outsources
- Where bargaining power sits along the value chain

Construct a company-specific value-chain map from critical inputs through production or service delivery to the end customer. Identify where the company adds value and where profits are captured.

### 4. Revenue architecture

Build the most granular defensible revenue tree available, separating revenue by:

- Product and service
- Reporting and economic segment
- Customer type and end market
- Geography
- Sales channel
- Contract and pricing model
- Recurring versus transactional source

For every material revenue stream, assess:

- Historical revenue and growth
- Price, volume, mix, acquisition, and currency contributions
- Gross-margin characteristics
- Customer acquisition method
- Contract length and renewal or replacement cycle
- Seasonality and cyclicality
- Capital intensity
- Relevant leading indicators
- Management's growth strategy and the evidence supporting it

Where the company does not disclose a useful breakdown, triangulate using customer disclosures, market size, operating metrics, shipment or usage data, and competitor information. Clearly label the result as an estimate.

### 5. Customers, channels, and demand

Investigate:

- Direct customers versus end customers
- Major named and probable customers
- Customer concentration and revenue dependency
- Customer industries, sizes, geographies, and budget sources
- Direct sales, distributors, resellers, retailers, marketplaces, and other channels
- Contract duration, renewal provisions, backlog, bookings, billings, and deferred revenue
- Churn, retention, net revenue retention, cohort behavior, or repeat-purchase patterns
- Customer acquisition cost, payback, sales productivity, and implementation requirements
- Switching costs, multi-sourcing, procurement cycles, and replacement cycles
- Exposure to customer capital expenditure, operating budgets, consumer income, credit, or government funding

Use reverse confirmation: search material customers' filings and public statements for their purchasing plans, inventories, capital expenditures, supplier strategy, product roadmaps, and demand outlook.

Produce a customer and channel table showing evidence, estimated materiality, relationship type, confidence level, and key risk.

### 6. Supply chain and operating footprint

Map the physical or digital supply chain, including:

- Critical raw materials, components, data, intellectual property, infrastructure, and services
- Named and probable suppliers
- Single-source and sole-source dependencies
- Contract manufacturers and outsourced service providers
- Manufacturing, assembly, distribution, data-center, office, and research locations
- Capacity, utilization, yields, bottlenecks, lead times, and expansion plans
- Minimum purchases, take-or-pay arrangements, purchase commitments, and supplier financing
- Inventory placement, obsolescence, write-downs, and working-capital requirements
- Freight methods, ports, routes, distribution centers, and logistics providers
- Tariffs, sanctions, export controls, currency, labour, energy, water, climate, and geopolitical exposures
- Supplier bargaining power and the cost and time required to qualify alternatives
- Business-continuity measures and evidence of actual redundancy

Consult company filings and sustainability reports, supplier announcements, customer disclosures, trade records, customs and shipment databases, certification databases, permits, recalls, product teardowns, facility-specific job postings, and credible local sources.

Do not assume shipping data are complete. Explicitly note potential omissions such as air freight, domestic movements, intermediary importers, subsidiaries, and private records.

Produce:

1. A supply-chain map
2. A material supplier and input table
3. A facility and capacity table
4. A geographic concentration and disruption-risk assessment

### 7. Geographic exposure

Analyze separately:

- Revenue by customer location
- Revenue by billing location
- Revenue by shipping destination
- Production and service-delivery location
- Long-lived assets by location
- Employees by location
- Suppliers and critical inputs by location
- Currency exposure
- Tax jurisdiction and profit allocation
- Regulatory and political exposure

Explain how the company defines its reported geographic figures. Do not treat different geographic measures as interchangeable.

### 8. Industry structure and competition

Define the relevant market narrowly enough to be useful. Assess:

- Market size, growth, penetration, and maturity
- Value-chain structure and industry profit pools
- Direct, indirect, emerging, and substitute competitors
- Market shares and the reliability of each estimate
- Customer and supplier bargaining power
- Barriers to entry and exit
- Regulation, standards, certifications, and distribution access
- Pricing behavior, capacity cycles, and competitive intensity
- Potential disruption from technology, business-model changes, or vertical integration

Compare the company with at least three appropriate peers, if available. Read competitor filings rather than relying only on third-party summaries.

Produce a peer table using consistently defined operating and financial metrics. Explain every important comparability limitation.

### 9. Competitive advantage and business quality

Test—not merely repeat—claims involving:

- Cost advantages
- Brand and trust
- Network effects
- Switching costs
- Intellectual property
- Proprietary data
- Regulation and approvals
- Scale purchasing or distribution
- Scarce assets
- Product integration
- Reliability, speed, service, or convenience

Look for evidence in gross margins, retention, market share, pricing, customer acquisition costs, sales efficiency, returns on capital, product performance, and competitor behavior.

Assess whether each advantage is strengthening, stable, weakening, or unproven. Identify the mechanism through which the advantage produces cash flow for shareholders.

### 10. Operating drivers and unit economics

Identify the few operational variables that explain the majority of revenue, margins, and cash flow. Examples include units, price, users, average revenue per user, stores, sales per store, capacity, utilization, yield, occupancy, transaction volume, take rate, subscribers, churn, backlog, reserves, production costs, load factor, claims, spreads, or credit losses.

Build company-specific driver equations. At minimum, decompose:

`Revenue = Volume × Price`, adjusted for mix, acquisition, divestiture, and currency where relevant.

Calculate unit economics where data permit. State definitions, periods, and assumptions. Test whether unit economics improve or deteriorate with scale.

### 11. Historical financial analysis

Present at least five fiscal years plus the latest trailing period, where available:

- Revenue and organic growth
- Gross profit and gross margin
- Operating expenses by major category
- Operating income and margin
- EBITDA only where economically meaningful, with reconciliation
- Net income and earnings per share
- Operating cash flow
- Capital expenditures divided between maintenance and growth where estimable
- Free cash flow using a clearly stated definition
- Working-capital components and cash-conversion cycle
- Net debt, liquidity, maturities, interest rates, and covenant headroom
- Share count, dilution, stock-based compensation, repurchases, and dividends
- Return on equity, return on assets, ROIC, and incremental ROIC

Reconcile GAAP or IFRS figures with management's adjusted measures. Identify recurring costs that management excludes, acquisition accounting effects, capitalization choices, unusual working-capital movements, and potential earnings-quality concerns.

### 12. Management, governance, and capital allocation

Evaluate:

- Management tenure, operational record, and relevant experience
- Board independence, skills, ownership, and conflicts
- Executive compensation metrics and whether they encourage per-share value creation
- Insider ownership, purchases, sales, pledges, and related-party transactions
- Guidance history and credibility
- Organic reinvestment returns
- Acquisition prices, strategic logic, integration, impairments, and realized returns
- Divestitures and portfolio decisions
- Debt issuance and repayment
- Repurchases relative to intrinsic value and dilution
- Dividend policy

Compare major historical management promises with subsequent outcomes. Present a capital-allocation scorecard covering at least the last five years.

### 13. Regulation, legal matters, and external dependencies

Investigate relevant securities, competition, environmental, labour, tax, product-safety, health, transportation, communications, banking, insurance, utility, energy, mining, privacy, cybersecurity, and industry-specific records.

Assess:

- Required licenses, approvals, certifications, and standards
- Material litigation, investigations, recalls, consent orders, and contingencies
- Environmental remediation and decommissioning obligations
- Pension and post-employment obligations
- Tax disputes and uncertain tax positions
- Cybersecurity and data dependencies
- Government incentives, reimbursements, procurement, or subsidies
- Policy changes capable of altering demand, cost, capacity, or market access

Separate current obligations from hypothetical risks.

### 14. Risk register and failure analysis

Create a ranked risk register. For every risk include:

- Causal mechanism
- Probability or qualitative likelihood
- Potential financial and operational impact
- Time horizon
- Leading indicators
- Possible mitigants
- Whether the risk is diversifiable, insurable, transferable, or structurally embedded
- Current evidence that the risk is increasing or decreasing

Include customer loss, supplier failure, capacity constraints, price competition, substitution, regulation, leverage, refinancing, dilution, accounting, execution, key-person, geographic, currency, commodity, litigation, cybersecurity, and governance risks where relevant.

Conduct a pre-mortem: describe three plausible paths by which the investment thesis could fail without relying on vague statements such as “macroeconomic weakness.”

### 15. Forecast and scenario analysis

Build bear, base, and bull operating scenarios for the requested forecast period. Each scenario must specify:

- Revenue drivers by material segment
- Price, volume, mix, and market-share assumptions
- Gross and operating margins
- Working capital
- Capital expenditure
- Taxes
- Financing costs
- Free cash flow
- Share count
- Key operational milestones

Link every major forecast assumption to historical evidence, management plans, industry data, capacity, contracts, or an explicitly stated analyst judgment.

Show sensitivities for the two to four variables with the greatest valuation impact. Ensure that the bear and bull cases represent different operating mechanisms, not arbitrary percentage changes.

### 16. Valuation and market expectations

Use methods appropriate to the company, potentially including:

- Discounted cash flow
- Comparable-company multiples
- Precedent transactions
- Sum-of-the-parts
- Net asset value or replacement value
- Dividend or residual-income approaches

Explain why each method is or is not appropriate. Reconcile enterprise value to equity value, including debt, cash, leases, pensions, minority interests, investments, options, and dilution.

Perform a reverse valuation or expectations analysis: estimate what revenue growth, margins, returns on capital, and duration of advantage would be required to justify the current market value.

Do not rely on a single-point price target. Present valuation ranges and identify which assumptions account for most of the range.

### 17. Variant view and monitoring plan

State:

- What the apparent market consensus is
- Where the evidence supports consensus
- Where a defensible variant view may exist
- Why the difference might persist
- What event or data would cause the market to revise its view

Create a monitoring dashboard containing:

- Leading operating indicators
- Customer and supplier indicators
- Pricing and capacity indicators
- Regulatory milestones
- Financial thresholds
- Thesis-confirming evidence
- Thesis-invalidating evidence
- Expected update frequency and source for each item

## Required Deliverable Structure

Deliver the final report in this order:

1. Research scope, cutoff date, and important limitations
2. Executive investment summary
3. Company snapshot
4. Corporate history and structure
5. Business model and value-chain map
6. Revenue architecture
7. Customer and channel analysis
8. Supply-chain and operating-footprint analysis
9. Geographic exposure
10. Industry and competitive landscape
11. Competitive advantage and business quality
12. Operating drivers and unit economics
13. Historical financial analysis
14. Management, governance, and capital allocation
15. Regulation, legal matters, and external dependencies
16. Ranked risk register and pre-mortem
17. Bear, base, and bull forecasts
18. Valuation and market-expectations analysis
19. Variant view
20. Monitoring dashboard
21. Unanswered questions and recommended further diligence
22. Source appendix

Use tables for exact comparisons and mappings. Use diagrams only where they materially improve the explanation of a value chain, corporate structure, supply chain, or customer flow.

## Mandatory Summary Tables

Include, where applicable:

- Revenue breakdown and driver table
- Customer and channel table
- Supplier and critical-input table
- Facility and capacity table
- Geographic exposure table
- Competitor comparison table
- Five-year financial and operating history
- Capital-allocation scorecard
- Risk register
- Scenario assumptions and outputs
- Valuation sensitivity table
- Thesis monitoring dashboard

## Citation and Evidence Format

For each material source, provide:

- Document or page title
- Issuer or publisher
- Filing or publication date
- Relevant fiscal period
- Direct URL
- Page, section, exhibit, or table reference where available
- Date accessed for dynamic sources

After important conclusions, include a compact evidence note identifying the strongest supporting source and any contradictory evidence.

At the end, provide a source ledger that classifies each source as primary, counterparty, competitor, government, industry, secondary, or alternative data.

## Quality-Control Checklist

Before submitting, verify that:

- Every major figure is sourced or reproducibly calculated
- Annual and quarterly periods have not been mixed incorrectly
- Fiscal years are distinguished from calendar years
- Currency translations and share-count adjustments are documented
- Continuing operations are separated from discontinued operations
- Organic growth is distinguished from acquisitions and foreign exchange
- Direct customers are distinguished from end customers
- Reported geography definitions are stated
- Supplier and customer names inferred from alternative data are labelled as probable, not confirmed
- Adjusted metrics are reconciled with reported metrics
- Free cash flow and ROIC definitions are explicit
- Stock-based compensation and dilution are not ignored
- Scenario assumptions agree internally across the income statement, balance sheet, and cash-flow statement
- Valuation uses the correct fully diluted share count and enterprise-value bridge
- Contradictory evidence is discussed
- Unanswered questions are preserved rather than filled with speculation
- The executive summary is consistent with the detailed analysis

## Final Analytical Test

The completed report must allow a reader to answer:

1. What creates the company's economic value?
2. Who ultimately pays the company, and why?
3. Which inputs, suppliers, facilities, channels, and relationships are indispensable?
4. What are the true revenue, margin, cash-flow, and return-on-capital drivers?
5. Why can or cannot competitors replicate the company's position?
6. How much capital is required to maintain and grow the business?
7. Is management converting business success into per-share shareholder value?
8. What could permanently impair the business or equity value?
9. What operating outcomes are already reflected in the market price?
10. Which observable evidence would confirm or invalidate the thesis?

If the available evidence cannot answer one of these questions, state that explicitly and identify the most useful next research step.
