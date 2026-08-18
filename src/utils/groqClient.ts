import { DetectionClassification, ModuleAuditResult } from '../types';

export interface GroqChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export const GROQ_MODELS = [
  { id: 'openai/gpt-oss-20b', name: 'OpenAI GPT-OSS 20B (16GB On-Premise Target)' },
  { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B Instant (Edge/Local Low-Footprint)' }
];

export async function testGroqConnection(apiKey: string, model = 'llama-3.1-8b-instant'): Promise<{ success: boolean; message: string }> {
  if (!apiKey || apiKey.trim() === '') {
    return { success: false, message: 'No Groq API key provided.' };
  }

  try {
    const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey.trim()}`
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: 'You are an API verification bot. Respond with: OK' },
          { role: 'user', content: 'Ping' }
        ],
        max_tokens: 10,
        temperature: 0.1
      })
    });

    if (!response.ok) {
      const errJson = await response.json().catch(() => ({}));
      const errMsg = errJson?.error?.message || `HTTP ${response.status}: ${response.statusText}`;
      return { success: false, message: `Groq verification failed: ${errMsg}` };
    }

    return { success: true, message: 'Groq API Key verified successfully!' };
  } catch (err: any) {
    return { success: false, message: `Network error connecting to Groq: ${err.message}` };
  }
}

export async function generateGroqAuditReport(
  apiKey: string,
  model: string,
  classification: DetectionClassification,
  auditResult: ModuleAuditResult,
  batchData: Record<string, any>[]
): Promise<string> {
  if (!apiKey || apiKey.trim() === '') {
    throw new Error('Groq API Key is required. Please enter your key in the sidebar.');
  }

  const prompt = `
You are AuditIQ Senior Forensic AI Auditor. Analyze this 5-record financial data batch:

DATA SEPARATION & CLASSIFICATION:
- Detected Category: ${classification.detectedType} (${classification.confidence}% confidence)
- Routed Detection Module: ${classification.routedModule}
- File Headers: ${Object.keys(batchData[0] || {}).join(', ')}

AUDIT ENGINE DETECTION SUMMARY:
- Total Records Tested: ${auditResult.totalRecords}
- Flagged Anomalies: ${auditResult.flaggedCount} (${auditResult.criticalCount} Critical, ${auditResult.highCount} High)
- Rule Engine Insights: ${auditResult.summaryInsights.join(' | ')}

DETAILED RECORD LEVEL FINDINGS:
${JSON.stringify(auditResult.records.map(r => ({
  row: r.rowIndex,
  id: r.recordId,
  status: r.status,
  riskScore: r.riskScore,
  flags: r.flags.map(f => ({ rule: f.ruleName, severity: f.severity, desc: f.description, remediation: f.remediation })),
  rawData: r.rawRecord
})), null, 2)}

Please generate a concise, professional, structured Forensic Audit Memo with the following sections:
1. Executive Risk Summary & Data Integrity Rating
2. Key Anomalies Diagnosed (referencing specific row numbers, dollar amounts, and rule violations)
3. Fraud / Non-Compliance Exposure (structuring, unrecorded liabilities, fictitious billing, or period-end distortion)
4. Recommended Immediate Workpaper & Internal Control Action Steps.

Keep your response crisp, authoritative, and direct (suitable for Chief Audit Executives and external audit partners).
`;

  const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey.trim()}`
    },
    body: JSON.stringify({
      model: model || 'llama-3.3-70b-versatile',
      messages: [
        {
          role: 'system',
          content: 'You are AuditIQ Lead Forensic Accounting AI, specializing in SOX compliance, internal control auditing, fraud detection, and data segregation.'
        },
        {
          role: 'user',
          content: prompt
        }
      ],
      temperature: 0.3,
      max_tokens: 1500
    })
  });

  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    throw new Error(errJson?.error?.message || `Groq API Error (${response.status})`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || 'No memo content returned from Groq.';
}

export async function groqClassifyAmbiguousColumns(
  apiKey: string,
  model: string,
  headers: string[],
  sampleRows: Record<string, any>[]
): Promise<{
  recommendedCategory: string;
  reasoning: string;
  suggestedColumnMapping: Record<string, string>;
}> {
  if (!apiKey || apiKey.trim() === '') {
    throw new Error('Groq API Key is required for AI column triage.');
  }

  const prompt = `
Analyze these ambiguous financial/operational data columns and sample rows:
Columns: ${JSON.stringify(headers)}
Sample Rows: ${JSON.stringify(sampleRows.slice(0, 3))}

Known Categories:
1. "transactions" (date, amount, vendor, account_code, approved_by, department)
2. "ar_ap_aging" (invoice_date, due_date, payment_date, amount, customer_vendor, invoice_status)
3. "general_ledger" (entry_date, account_name, debit, credit, journal_reference, prepared_by)
4. "fixed_assets" (asset_name, purchase_date, purchase_cost, depreciation_method, useful_life, current_value)
5. "unknown" (if completely non-financial)

Respond ONLY in valid JSON with this exact format:
{
  "recommendedCategory": "transactions" | "ar_ap_aging" | "general_ledger" | "fixed_assets" | "unknown",
  "reasoning": "string explaining why based on data types and values",
  "suggestedColumnMapping": {
    "raw_header_name": "canonical_header_name"
  }
}
`;

  const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey.trim()}`
    },
    body: JSON.stringify({
      model: model || 'llama-3.3-70b-versatile',
      messages: [
        { role: 'system', content: 'You are an expert financial schema mapper. Output valid JSON only.' },
        { role: 'user', content: prompt }
      ],
      response_format: { type: 'json_object' },
      temperature: 0.1
    })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err?.error?.message || `Groq API Error (${response.status})`);
  }

  const data = await response.json();
  const content = data.choices?.[0]?.message?.content || '{}';
  return JSON.parse(content);
}
