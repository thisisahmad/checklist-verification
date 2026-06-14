import json
from parser import parse_supporting_file
from rule_engine import evaluate_rule
import pandas as pd
from app_logging import get_logger, start_run_log, get_run_log_text

logger = get_logger("verifier")


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _score_bucket(score):
    if score >= 90:
        return 'Excellent'
    if score >= 80:
        return 'Strong'
    if score >= 65:
        return 'Needs Review'
    if score >= 50:
        return 'High Risk'
    return 'Critical'


def _risk_level(score):
    if score >= 80:
        return 'Low'
    if score >= 65:
        return 'Medium'
    if score >= 50:
        return 'High'
    return 'Critical'


def _weighted_score(items):
    total_weight = sum(_safe_float(item.get('weight'), 1.0) for item in items)
    if total_weight == 0:
        return 0
    weighted = sum(item.get('score', 0) * _safe_float(item.get('weight'), 1.0) for item in items)
    return round(weighted / total_weight)


def _build_category_scores(items):
    if not items:
        return []
    rows = []
    for category, group in pd.DataFrame(items).groupby('category', dropna=False):
        records = group.to_dict('records')
        score = _weighted_score(records)
        rows.append({
            'category': category or 'Uncategorized',
            'score': score,
            'risk': _risk_level(score),
            'checks': len(records),
            'passed': int((group['status'] == 'PASS').sum()),
            'partial': int((group['status'] == 'PARTIAL').sum()),
            'failed': int((group['status'] == 'FAIL').sum()),
        })
    return rows


def _build_all_rules(checklist_df, rules_df):
    checklist_rule_cols = {'rule_type', 'rule_spec', 'confidence_threshold'}
    has_embedded_rules = checklist_rule_cols.issubset(set(map(str, checklist_df.columns)))
    embedded_rules = []
    if has_embedded_rules:
        for _, chk in checklist_df.iterrows():
            rtype = str(chk.get('rule_type') or '').strip()
            rspec = chk.get('rule_spec') or ''
            if rtype or rspec:
                embedded_rules.append({
                    'id': chk.get('id') or '',
                    'check_id': chk.get('id') or '',
                    'rule_type': rtype,
                    'rule_spec': rspec if isinstance(rspec, str) else json.dumps(rspec),
                    'confidence_threshold': chk.get('confidence_threshold') or 0.75,
                })
    embedded_df = pd.DataFrame(embedded_rules) if embedded_rules else pd.DataFrame(
        columns=['id', 'check_id', 'rule_type', 'rule_spec', 'confidence_threshold']
    )

    if rules_df is None or rules_df.empty:
        rules_df = pd.DataFrame(columns=['id', 'check_id', 'rule_type', 'rule_spec', 'confidence_threshold'])
    for col in ['id', 'check_id', 'rule_type', 'rule_spec', 'confidence_threshold']:
        if col not in rules_df.columns:
            rules_df[col] = ''

    frames = [df for df in [rules_df, embedded_df] if not df.empty]
    if frames:
        return pd.concat(frames, ignore_index=True)
    return pd.DataFrame(columns=['id', 'check_id', 'rule_type', 'rule_spec', 'confidence_threshold'])


def _item_result(chk, rule, parsed, use_llm, llm_model):
    res = evaluate_rule(rule, parsed, use_llm=use_llm, llm_model=llm_model)
    return {
        'check_id': chk.get('id'),
        'item_text': chk.get('item_text'),
        'category': chk.get('category') or 'Uncategorized',
        'weight': _safe_float(chk.get('weight'), 1.0) or 1.0,
        'rule_id': rule.get('id', ''),
        'rule_type': rule.get('rule_type', ''),
        **res,
    }


def run_verification(checklist_df, rules_df, support_files, use_llm=False, llm_model='gpt-5'):
    start_run_log()
    support_files = list(support_files)
    logger.info(
        "Run config | checklist_items=%s | documents=%s | use_llm=%s | model=%s",
        len(checklist_df),
        len(support_files),
        use_llm,
        llm_model if use_llm else "n/a",
    )
    documents = []
    all_rules = _build_all_rules(checklist_df, rules_df)
    logger.info("Rules prepared | total_rules=%s", len(all_rules))

    for f in support_files:
        parsed = parse_supporting_file(f)
        logger.info("Evaluating document | name=%s", parsed['name'])
        items = []
        for _, chk in checklist_df.iterrows():
            cid = chk.get('id')
            relevant_rules = all_rules[all_rules['check_id'] == cid]
            if relevant_rules.shape[0] == 0:
                rule_row = {'rule_type': 'boolean', 'rule_spec': json.dumps({'keyword': chk.get('item_text')}), 'confidence_threshold': 0.75}
                items.append(_item_result(chk, rule_row, parsed, use_llm, llm_model))
            else:
                for _, r in relevant_rules.iterrows():
                    items.append(_item_result(chk, r, parsed, use_llm, llm_model))

        doc_score = _weighted_score(items)
        status_counts = pd.Series([item['status'] for item in items]).value_counts().to_dict() if items else {}
        passed = int(status_counts.get('PASS', 0))
        partial = int(status_counts.get('PARTIAL', 0))
        failed = int(status_counts.get('FAIL', 0))
        documents.append({
            'name': parsed['name'],
            'score': doc_score,
            'bucket': _score_bucket(doc_score),
            'risk': _risk_level(doc_score),
            'checks': len(items),
            'passed': passed,
            'partial': partial,
            'failed': failed,
            'pass_rate': round((passed / len(items)) * 100) if items else 0,
            'fields_detected': len(parsed.get('fields', {})),
            'text_length': len(parsed.get('text', '')),
            'category_scores': _build_category_scores(items),
            'items': items,
        })
        logger.info(
            "Document complete | name=%s | score=%s | passed=%s | partial=%s | failed=%s",
            parsed['name'],
            doc_score,
            passed,
            partial,
            failed,
        )

    overall = round(sum(d['score'] for d in documents) / len(documents)) if documents else 0
    summary = [{
        'Document': d['name'],
        'Score': d['score'],
        'Rating': d['bucket'],
        'Risk': d['risk'],
        'Checks': d['checks'],
        'Passed': d['passed'],
        'Partial': d['partial'],
        'Failed': d['failed'],
        'Pass Rate %': d['pass_rate'],
        'Fields Detected': d['fields_detected'],
    } for d in documents]

    all_category_rows = []
    llm_error_count = 0
    for doc in documents:
        llm_error_count += sum(1 for item in doc['items'] if item.get('llm_error'))
        for row in doc['category_scores']:
            all_category_rows.append({'document': doc['name'], **row})

    category_summary = pd.DataFrame(all_category_rows)
    if not category_summary.empty:
        category_summary = (
            category_summary.groupby('category', as_index=False)
            .agg(score=('score', 'mean'), checks=('checks', 'sum'), passed=('passed', 'sum'), partial=('partial', 'sum'), failed=('failed', 'sum'))
        )
        category_summary['score'] = category_summary['score'].round().astype(int)
        category_summary['risk'] = category_summary['score'].apply(_risk_level)

    overall_status = _score_bucket(overall)
    logger.info(
        "Run complete | overall_score=%s | status=%s | risk=%s | llm_errors=%s",
        overall,
        overall_status,
        _risk_level(overall),
        llm_error_count,
    )
    logger.info("=" * 60)
    return {
        'documents': documents,
        'overall_score': overall,
        'overall_status': overall_status,
        'overall_risk': _risk_level(overall),
        'summary_table': pd.DataFrame(summary),
        'category_summary': category_summary,
        'llm_model': llm_model if use_llm else 'Rule-based only',
        'llm_error_count': llm_error_count,
        'run_log': get_run_log_text(),
    }
