import { DetectionClassification, ModuleAuditResult } from '../types';

export interface GroqChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export const GROQ_MODELS = [
  { id: 'openai/gpt-oss-20b', name: 'OpenAI GPT-OSS 20B (16GB On-Premise Target)' },
  { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B Instant (Edge/Local Low-Footprint)' }
];

/**
 * Helper to call Groq API with exponential backoff for HTTP 429 Rate Limits
 */
async function fetchGroqWithRetry(
  apiKey: string,
  bodyPayload: Record<string, any>,
  maxRetries = 3
): Promise<Response> {
  const cleanedKey = apiKey.trim();
  let lastError: any = null;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${cleanedKey}`
        },
        body: JSON.stringify(bodyPayload)
      });

      if (response.status === 429 && attempt < maxRetries - 1) {
        // Exponential backoff + random jitter: 2s, 4s, 8s
        const delay = Math.pow(2, attempt + 1) * 1000 + Math.random() * 1000;
        await new Promise(resolve => setTimeout(resolve, delay));
        continue;
      }

      return response;
    } catch (err: any) {
      lastError = err;
      if (attempt < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, 1500));
        continue;
      }
    }
  }

  throw lastError || new Error('Network error calling Groq after retries.');
}

export async function testGroqConnection(apiKey: string, model = 'llama-3.1-8b-instant'): Promise<{ success: boolean; message: string }> {
  if (!apiKey || apiKey.trim() === '') {
    return { success: false, message: 'No Groq API key provided.' };
  }

  try {
    const response = await fetchGroqWithRetry(apiKey, {
      model,
      messages: [
        { role: 'system', content: 'You are an API verification bot. Respond strictly with: OK' },
        { role: 'user', content: 'Ping' }
      ],
      max_tokens: 10,
      temperature: 0.1
    }, 2);

    if (!response.ok) {
      const errJson = await response.json().catch(() => ({}));
      const errMsg = errJson?.error?.message || `HTTP ${response.status}: ${response.statusText}`;
      return { success: false, message: `Groq verification failed: ${errMsg}` };
    }

    return { success: true, message: `Connected to ${model} successfully!` };
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

  // Concise payload to conserve Groq TPM budget
  const conciseFindings = auditResult.records.slice(0, 5).map(r => ({
    row: r.rowIndex,
    status: r.status,
    riskScore: r.riskScore,
    flags: r.flags.map(f => ({
      code: f.ruleCode || f.id,
      name: f.ruleName,
      severity: f.severity,
      detectedValue: f.actualValue ?? ''
    })),
    raw: r.rawRecord
  }));

  const prompt = `
You are AuditIQ Senior Forensic AI Auditor and Chartered Accountant.
Evaluate this 5-record financial data batch and draft a formal 5C Internal Audit Workpaper Memo.

DATA SEGREGATION & CLASSIFICATION:
- Detected Category: ${classification.detectedType} (${classification.confidence}% confidence)
- Routed Module: ${classification.routedModule}

BATCH LEVEL DETERMINISTIC FINDINGS:
${JSON.stringify(conciseFindings, null, 2)}

FORMAT INSTRUCTIONS:
Structure your workpaper strictly adhering to the 5C Internal Audit Standard:

# FORENSIC AUDIT WORKPAPER MEMO
**Engagement:** Automated Data Segregation & Internal Control Testing
**Audit Domain:** ${classification.detectedType.toUpperCase()}
**Rule Verification:** 100% Deterministic Vector Engine (AI Drafts Workpaper)

## 1. CONDITION (Factual Observations)
Document specific anomalies detected in this batch with exact Row #, INR amounts (formatted in ₹), counterparty names, and triggered rule codes.

## 2. CRITERIA (Governing Accounting & Control Rules)
Cite applicable internal authorization policies (e.g. ₹50,000 threshold), ICAI standards, or SOX-404 segregation of duties requirements.

## 3. CAUSE (Root Process Failure)
Identify why the breakdown occurred (e.g. absent maker-checker approvals, deliberate invoice structuring, backdated timestamps, or unmonitored suspense entries).

## 4. CONSEQUENCE (Financial & Compliance Exposure)
Quantify exposure (e.g. unrecorded liabilities, unauthorized disbursements, or audit qualification risk).

## 5. CORRECTIVE ACTION (Remediation Protocol)
Actionable next steps for internal management and the CA audit engagement team prior to workpaper sign-off.
`;

  const response = await fetchGroqWithRetry(apiKey, {
    model: model || 'openai/gpt-oss-20b',
    messages: [
      {
        role: 'system',
        content: 'You are AuditIQ Lead Forensic Accounting AI, specializing in SOX compliance, ICAI standards, internal control auditing, and fraud risk assessment.'
      },
      {
        role: 'user',
        content: prompt
      }
    ],
    temperature: 0.2,
    max_tokens: 1500
  });

  if (!response.ok) {
    const errJson = await response.json().catch(() => ({}));
    throw new Error(errJson?.error?.message || `Groq API Error (${response.status})`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || 'No memo content returned from Groq.';
}

export async function suggestColumnMappingWithGroq(
  apiKey: string,
  model: string,
  headers: string[],
  sampleRows: Record<string, any>[],
  targetCategory?: string
): Promise<Record<string, string>> {
  const result = await groqClassifyAmbiguousColumns(apiKey, model, headers, sampleRows);
  return result.suggestedColumnMapping || {};
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

  const response = await fetchGroqWithRetry(apiKey, {
    model: model || 'openai/gpt-oss-20b',
    messages: [
      { role: 'system', content: 'You are an expert financial schema mapper. Output valid JSON only.' },
      { role: 'user', content: prompt }
    ],
    response_format: { type: 'json_object' },
    temperature: 0.1
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err?.error?.message || `Groq API Error (${response.status})`);
  }

  const data = await response.json();
  const content = data.choices?.[0]?.message?.content || '{}';
  return JSON.parse(content);
}
