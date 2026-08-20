import { ColumnSignature, DetectionClassification, FinancialDataType, MatchScore } from '../types';

export const SIGNATURES: ColumnSignature[] = [
  {
    category: 'transactions',
    displayName: 'Operational Transactions',
    description: 'Procurement, vendor spend, operational disbursements, and departmental expenses.',
    targetModule: 'Transaction Anomaly Detection Engine (Approval & Structuring)',
    primaryHeaders: ['date', 'amount', 'vendor', 'account_code', 'approved_by', 'department'],
    secondaryHeaders: ['transaction_id', 'description', 'payment_method', 'currency', 'receipt_attached'],
    aliasMap: {
      date: ['date', 'txn_date', 'transaction_date', 'trans_date', 'spend_date', 'posting_date', 'timestamp'],
      amount: ['amount', 'txn_amount', 'total_amount', 'cost', 'spend', 'amount_inr', 'amount_usd', 'subtotal', 'charge'],
      vendor: ['vendor', 'supplier', 'payee', 'merchant', 'vendor_name', 'counterparty', 'contractor', 'seller'],
      account_code: ['account_code', 'account_no', 'gl_code', 'expense_code', 'cost_code', 'chart_of_accounts'],
      approved_by: ['approved_by', 'approver', 'authorized_by', 'signer', 'approved', 'approval_user', 'manager'],
      department: ['department', 'dept', 'cost_center', 'division', 'business_unit', 'team', 'branch']
    }
  },
  {
    category: 'ar_ap_aging',
    displayName: 'Accounts Receivable / Payable Aging',
    description: 'Customer billings, vendor invoices, due dates, aging buckets, and settlement timing.',
    targetModule: 'AR/AP Aging Anomaly Engine (Overdue & Payment Velocity)',
    primaryHeaders: ['invoice_date', 'due_date', 'payment_date', 'amount', 'customer_vendor', 'invoice_status'],
    secondaryHeaders: ['invoice_number', 'terms', 'aging_bucket', 'days_overdue', 'currency', 'discount'],
    aliasMap: {
      invoice_date: ['invoice_date', 'inv_date', 'bill_date', 'doc_date', 'issue_date', 'origination_date'],
      due_date: ['due_date', 'maturity_date', 'payment_due', 'due', 'expiry_date', 'expected_date'],
      payment_date: ['payment_date', 'paid_date', 'settlement_date', 'cleared_date', 'remittance_date', 'paid_on'],
      amount: ['amount', 'invoice_amount', 'balance', 'outstanding_amount', 'open_amount', 'total_billed', 'net_due'],
      customer_vendor: ['customer_vendor', 'customer', 'vendor', 'client', 'customer_name', 'vendor_name', 'debtor', 'creditor', 'counterparty', 'payer'],
      invoice_status: ['invoice_status', 'status', 'payment_status', 'aging_status', 'state', 'inv_status']
    }
  },
  {
    category: 'general_ledger',
    displayName: 'General Ledger / Journal Entries',
    description: 'Double-entry journal batches, debit/credit allocations, GL trial accounts, and period adjustments.',
    targetModule: 'GL / Journal Entry Engine (Balance, Off-Hours & Period-End)',
    primaryHeaders: ['entry_date', 'account_name', 'debit', 'credit', 'journal_reference', 'prepared_by'],
    secondaryHeaders: ['line_number', 'description', 'entity_id', 'currency', 'is_manual', 'posted_time'],
    aliasMap: {
      entry_date: ['entry_date', 'posting_date', 'je_date', 'effective_date', 'txn_timestamp', 'journal_date'],
      account_name: ['account_name', 'account_description', 'gl_account', 'account_title', 'account', 'ledger_account', 'account_code'],
      debit: ['debit', 'dr', 'debit_amount', 'dr_amount', 'debits'],
      credit: ['credit', 'cr', 'credit_amount', 'cr_amount', 'credits'],
      journal_reference: ['journal_reference', 'je_number', 'ref_number', 'journal_id', 'batch_id', 'voucher_no', 'reference', 'journal_ref', 'entry_id'],
      prepared_by: ['prepared_by', 'created_by', 'entered_by', 'posted_by', 'user_id', 'author', 'originator']
    }
  },
  {
    category: 'fixed_assets',
    displayName: 'Fixed Asset Register',
    description: 'Capital assets, acquisition values, depreciation schedules, and carrying book value reconciliations.',
    targetModule: 'Fixed Asset Reconciliation Engine (Valuation & Schedule Discrepancy)',
    primaryHeaders: ['asset_name', 'purchase_date', 'purchase_cost', 'depreciation_method', 'useful_life', 'current_value'],
    secondaryHeaders: ['asset_id', 'asset_tag', 'serial_number', 'accumulated_depreciation', 'salvage_value', 'location'],
    aliasMap: {
      asset_name: ['asset_name', 'asset_description', 'equipment_name', 'asset_title', 'item_name', 'asset'],
      purchase_date: ['purchase_date', 'acquisition_date', 'in_service_date', 'installed_date', 'cap_date', 'buy_date'],
      purchase_cost: ['purchase_cost', 'original_cost', 'acquisition_cost', 'initial_cost', 'historical_cost', 'gross_book_value', 'cost'],
      depreciation_method: ['depreciation_method', 'depr_method', 'method', 'depreciation_type', 'depr_type'],
      useful_life: ['useful_life', 'useful_life_years', 'asset_life', 'lifespan_years', 'life_years', 'life'],
      current_value: ['current_value', 'book_value', 'net_book_value', 'carrying_value', 'residual_value', 'current_book_value', 'nbv']
    }
  }
];

export function normalizeHeader(header: string): string {
  return String(header || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

/**
 * Token-boundary alias matcher preventing false positives like 'dr' in 'address'
 */
export function aliasMatchesHeader(alias: string, normHeader: string): boolean {
  if (!alias || !normHeader) return false;
  const normAlias = normalizeHeader(alias);
  if (normAlias === normHeader) return true;

  const tokens = normHeader.split('_');
  if (normAlias.length <= 3) {
    return tokens.includes(normAlias);
  }

  if (tokens.includes(normAlias)) return true;

  // Boundary regex: must be bounded by start/end of string or underscores
  const regex = new RegExp(`(^|_)${normAlias}(_|$)`);
  return regex.test(normHeader);
}

/**
 * Calculates matching score between uploaded raw headers and target signatures
 */
export function classifyFinancialData(headers: string[]): DetectionClassification {
  if (!headers || headers.length === 0) {
    return {
      detectedType: 'ambiguous',
      confidence: 0,
      isAmbiguous: true,
      scores: [],
      matchedColumns: {},
      unmatchedHeaders: [],
      reasons: ['No columns detected in the uploaded file.'],
      routedModule: 'Unassigned (Awaiting Confirmation)'
    };
  }

  const normalizedHeaders = headers.map(h => ({
    raw: h,
    norm: normalizeHeader(h)
  }));

  const scores: MatchScore[] = SIGNATURES.map(signature => {
    const matchedPrimary: string[] = [];
    const matchedSecondary: string[] = [];
    const missingCritical: string[] = [];
    const matchedHeaderMap: Record<string, string> = {};

    // Check primary headers using token-boundary match
    for (const primaryKey of signature.primaryHeaders) {
      const aliases = signature.aliasMap[primaryKey] || [primaryKey];
      
      const foundMatch = normalizedHeaders.find(nh => {
        return aliases.some(alias => aliasMatchesHeader(alias, nh.norm));
      });

      if (foundMatch) {
        matchedPrimary.push(primaryKey);
        matchedHeaderMap[foundMatch.raw] = primaryKey;
      } else {
        missingCritical.push(primaryKey);
      }
    }

    // Check secondary headers
    for (const secKey of signature.secondaryHeaders) {
      const foundMatch = normalizedHeaders.find(nh => aliasMatchesHeader(secKey, nh.norm));
      if (foundMatch && !matchedHeaderMap[foundMatch.raw]) {
        matchedSecondary.push(secKey);
      }
    }

    // Primary matches are weighted 85%, secondary 15%
    const primaryRatio = matchedPrimary.length / signature.primaryHeaders.length;
    const secondaryRatio = signature.secondaryHeaders.length > 0
      ? Math.min(1, matchedSecondary.length / 2)
      : 0;

    let score = Math.round((primaryRatio * 85) + (secondaryRatio * 15));

    // Penalty if critical primary indicators are totally absent
    if (signature.category === 'general_ledger') {
      const hasDebitCredit = matchedPrimary.includes('debit') || matchedPrimary.includes('credit');
      if (!hasDebitCredit) score = Math.min(score, 30);
    }
    if (signature.category === 'fixed_assets') {
      const hasAssetOrCost = matchedPrimary.includes('asset_name') || matchedPrimary.includes('purchase_cost');
      if (!hasAssetOrCost) score = Math.min(score, 30);
    }
    if (signature.category === 'ar_ap_aging') {
      const hasDueDateOrStatus = matchedPrimary.includes('due_date') || matchedPrimary.includes('invoice_status');
      if (!hasDueDateOrStatus) score = Math.min(score, 30);
    }

    let confidenceLevel: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE' = 'NONE';
    if (score >= 70) confidenceLevel = 'HIGH';
    else if (score >= 45) confidenceLevel = 'MEDIUM';
    else if (score >= 20) confidenceLevel = 'LOW';

    return {
      category: signature.category,
      displayName: signature.displayName,
      score,
      matchedPrimary,
      matchedSecondary,
      confidenceLevel,
      missingCritical
    };
  });

  // Sort by score descending
  scores.sort((a, b) => b.score - a.score);

  const topMatch = scores[0];
  const detectedType: FinancialDataType = topMatch && topMatch.score >= 50
    ? topMatch.category
    : 'ambiguous';

  const isAmbiguous = detectedType === 'ambiguous';
  const matchedColumns: Record<string, string> = {};
  const unmatchedHeaders: string[] = [];
  const reasons: string[] = [];

  if (topMatch && !isAmbiguous) {
    const signature = SIGNATURES.find(s => s.category === topMatch.category)!;
    reasons.push(`Matched ${topMatch.matchedPrimary.length} of ${signature.primaryHeaders.length} primary signature headers for ${signature.displayName}.`);
    
    if (topMatch.matchedSecondary.length > 0) {
      reasons.push(`Found supplementary headers: ${topMatch.matchedSecondary.join(', ')}.`);
    }
    
    // Map headers for topMatch
    for (const nh of normalizedHeaders) {
      let mapped = false;
      for (const pKey of signature.primaryHeaders) {
        const aliases = signature.aliasMap[pKey] || [pKey];
        if (aliases.some(a => aliasMatchesHeader(a, nh.norm))) {
          matchedColumns[nh.raw] = pKey;
          mapped = true;
          break;
        }
      }
      if (!mapped) {
        unmatchedHeaders.push(nh.raw);
      }
    }
  } else {
    reasons.push('Column headers do not unambiguously conform to a known financial data template.');
    if (topMatch && topMatch.score > 0) {
      reasons.push(`Closest match "${topMatch.displayName}" only scored ${topMatch.score}% confidence (insufficient for automated routing).`);
    }
    headers.forEach(h => unmatchedHeaders.push(h));
  }

  const activeSignature = SIGNATURES.find(s => s.category === detectedType);
  const routedModule = activeSignature 
    ? activeSignature.targetModule 
    : 'Segregation Triage (User Confirmation Required)';

  return {
    detectedType,
    confidence: topMatch ? topMatch.score : 0,
    isAmbiguous,
    scores,
    matchedColumns,
    unmatchedHeaders,
    reasons,
    routedModule
  };
}

export function getCategoryFields(category: FinancialDataType): string[] {
  const sig = SIGNATURES.find(s => s.category === category);
  return sig ? sig.primaryHeaders : ['date', 'amount', 'vendor', 'account_code', 'approved_by', 'department'];
}
