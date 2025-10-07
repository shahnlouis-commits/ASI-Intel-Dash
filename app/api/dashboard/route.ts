// app/api/dashboard/route.ts (Restored Code)
import { NextResponse } from "next/server"

export async function GET() {
  // Use the ORIGINAL GitHub JSON URL
  const githubUrl = "https://github.com/shahnlouis-commits/ASI-Intel-Dash/raw/refs/heads/main/DashData"

  const fallbackData = [
    // Your original fallback data goes here
    {
      type: "Medium Priority",
      category: "Regional Analysis",
      country: "Myanmar",
      date: "2025-08-25",
      headline: "Myanmar Junta, Asset or Liability?",
      body: "While future U.S. recognition and engagement with the military junta in Myanmar may seem like a great deal to access key minerals, civil war in the country may make stability of access tough sell.",
    },
    {
      type: "Strategic Watch",
      category: "Supply Chain Risk",
      country: "United States",
      date: "2025-08-24",
      headline: "Renewed Tariffs on Key Commodities",
      body: "A new round of protectionist tariffs on steel and aluminum from trade partners is causing price volatility and supply chain disruptions. Businesses should audit existing supplier contracts.",
    },
    {
      type: "Forecast Alert",
      category: "Threat Forecasting",
      country: "Global",
      date: "2025-08-22",
      headline: "Cyber Threats Shift to AI-Enabled Social Engineering",
      body: "Adversaries are leveraging generative AI to create more sophisticated and convincing social engineering attacks. Companies need to update security protocols and employee training to counter this threat.",
    },
    {
      type: "Medium Priority",
      category: "Policy Changes",
      country: "European Union",
      date: "2025-08-18",
      headline: "New Regulations for AI Governance",
      body: "The EU's recent AI Act is setting a global precedent for artificial intelligence governance, and its provisions may impact U.S. companies operating in Europe. Businesses should evaluate their AI usage for compliance.",
    },
  ]

  try {
    const response = await fetch(githubUrl, {
      method: "GET",
      headers: {
        Accept: "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; Dashboard/1.0)",
      },
      redirect: "follow",
      next: { revalidate: 300 },
    })

    if (!response.ok) {
      return NextResponse.json(fallbackData)
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    return NextResponse.json(fallbackData)
  }
}
