import json
import re
from difflib import SequenceMatcher
from crewai_orchestrator import explain_verification
from app_logging import get_logger

logger = get_logger("rules")


def semantic_similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _normalize_outcome(outcome):
    outcome = str(outcome or '').upper()
    return outcome if outcome in {'PASS', 'PARTIAL', 'FAIL'} else None


def _field_key(label):
    return re.sub(r'[^a-z0-9_]', '', str(label or '').lower().replace(' ', '_'))


def _keyword_present(keyword, parsed_doc):
    fields = parsed_doc.get('fields', {})
    field_key = _field_key(keyword)
    if fields and (' ' in str(keyword) or '_' in str(keyword)):
        value = fields.get(field_key)
        return value not in (None, '', [])
    return str(keyword or '').lower() in (parsed_doc.get('text') or '').lower()


def _apply_llm_review(rule_for_llm, parsed_doc, model):
    snippet = parsed_doc.get('text', '')[:4000]
    llm_res = explain_verification(rule_for_llm, snippet, model=model)
    llm_error = bool(llm_res.get('llm_error'))
    return {
        'llm_outcome': None if llm_error else _normalize_outcome(llm_res.get('outcome')),
        'llm_confidence': _safe_float(llm_res.get('confidence')) or 0.0,
        'llm_explanation': llm_res.get('explanation', ''),
        'llm_evidence': llm_res.get('evidence', ''),
        'llm_missing_info': llm_res.get('missing_info', ''),
        'llm_recommendation': llm_res.get('recommendation', ''),
        'llm_error': llm_error,
    }


def evaluate_rule(rule_row, parsed_doc, use_llm=False, llm_model='gpt-5'):
    if hasattr(rule_row, 'get'):
        rtype = str(rule_row.get('rule_type', '')).strip().lower()
        spec_raw = rule_row.get('rule_spec', '')
        conf_thresh = _safe_float(rule_row.get('confidence_threshold')) or 0.75
    else:
        rtype = str(rule_row.rule_type).strip().lower()
        spec_raw = rule_row.rule_spec
        conf_thresh = _safe_float(rule_row.confidence_threshold) or 0.75

    try:
        spec = json.loads(spec_raw) if isinstance(spec_raw, str) and spec_raw.strip().startswith('{') else {}
    except Exception:
        spec = {}

    explanation = ''
    confidence = 0.0
    passed = False
    llm_outcome = None
    llm_confidence = None
    llm_explanation = None
    llm_evidence = ''
    llm_missing_info = ''
    llm_recommendation = ''
    llm_error = False
    expected = ''
    actual = ''
    reason_code = 'UNSUPPORTED_RULE'
    status = 'FAIL'

    if rtype == 'boolean':
        keyword = spec.get('keyword') or spec.get('field') or ''
        expected = f"Document should include '{keyword}'."
        present = _keyword_present(keyword, parsed_doc)
        actual = 'Required field found' if present else 'Required field missing'
        confidence = 1.0 if present else 0.0
        explanation = f"Keyword '{keyword}' {'found' if present else 'not found'}."
        passed = present
        reason_code = 'KEYWORD_FOUND' if present else 'KEYWORD_MISSING'
        if use_llm:
            rule_for_llm = {'rule_type': rtype, 'rule_spec': spec, 'confidence_threshold': conf_thresh}
            llm = _apply_llm_review(rule_for_llm, parsed_doc, llm_model)
            llm_outcome = llm['llm_outcome']
            llm_confidence = llm['llm_confidence']
            llm_explanation = llm['llm_explanation']
            llm_evidence = llm['llm_evidence']
            llm_missing_info = llm['llm_missing_info']
            llm_recommendation = llm['llm_recommendation']
            llm_error = llm['llm_error']
            confidence = max(confidence, llm_confidence)
            if llm_outcome == 'FAIL':
                passed = False
            elif llm_outcome == 'PASS':
                passed = True
            explanation += f" | LLM: {llm_explanation}"

    elif rtype == 'threshold':
        field = spec.get('field')
        operator = spec.get('operator')
        value = spec.get('value')
        doc_val = parsed_doc.get('fields', {}).get(field)
        expected = f"{field} {operator} {value}"
        actual = doc_val if doc_val not in (None, '') else 'Missing'
        try:
            doc_val = float(doc_val)
            target = float(value)
            if operator == '>=':
                passed = doc_val >= target
            elif operator == '<=':
                passed = doc_val <= target
            elif operator == '>':
                passed = doc_val > target
            elif operator == '<':
                passed = doc_val < target
            else:
                passed = doc_val == target
            confidence = 1.0 if passed else 0.0
            explanation = f"{field}={doc_val} {'meets' if passed else 'fails'} {operator}{target}"
            reason_code = 'THRESHOLD_MET' if passed else 'THRESHOLD_FAILED'
        except Exception:
            confidence = 0.0
            explanation = f"Could not parse numeric field {field}."
            reason_code = 'FIELD_MISSING_OR_INVALID'
        if use_llm:
            rule_for_llm = {'rule_type': rtype, 'rule_spec': spec, 'confidence_threshold': conf_thresh}
            llm = _apply_llm_review(rule_for_llm, parsed_doc, llm_model)
            llm_outcome = llm['llm_outcome']
            llm_confidence = llm['llm_confidence']
            llm_explanation = llm['llm_explanation']
            llm_evidence = llm['llm_evidence']
            llm_missing_info = llm['llm_missing_info']
            llm_recommendation = llm['llm_recommendation']
            llm_error = llm['llm_error']
            confidence = max(confidence, llm_confidence)
            if llm_outcome == 'FAIL':
                passed = False
            elif llm_outcome == 'PASS':
                passed = True
            explanation += f" | LLM: {llm_explanation}"

    elif rtype == 'semantic_match':
        left_field = spec.get('left')
        right_field = spec.get('right')
        left = parsed_doc.get('fields', {}).get(left_field) or ''
        right = parsed_doc.get('fields', {}).get(right_field) or ''
        sim = semantic_similarity(str(left), str(right))
        threshold = _safe_float(spec.get('similarity')) or 0.85
        expected = f"{left_field} should match {right_field} with similarity >= {threshold}"
        actual = f"{sim:.2f}"
        confidence = sim
        explanation = f"Semantic similarity between {left_field} and {right_field}: {sim:.2f}"
        passed = sim >= threshold
        reason_code = 'SEMANTIC_MATCH' if passed else 'SEMANTIC_MISMATCH'
        if use_llm:
            rule_for_llm = {'rule_type': rtype, 'rule_spec': spec, 'confidence_threshold': conf_thresh}
            llm = _apply_llm_review(rule_for_llm, parsed_doc, llm_model)
            llm_outcome = llm['llm_outcome']
            llm_confidence = llm['llm_confidence']
            llm_explanation = llm['llm_explanation']
            llm_evidence = llm['llm_evidence']
            llm_missing_info = llm['llm_missing_info']
            llm_recommendation = llm['llm_recommendation']
            llm_error = llm['llm_error']
            confidence = max(confidence, llm_confidence)
            explanation += " | LLM: " + llm_explanation
            if llm_outcome == 'FAIL':
                passed = False
            elif llm_outcome == 'PASS':
                passed = True

    else:
        keyword = spec.get('keyword') or rule_row.get('rule_spec') or ''
        expected = f"Document should include '{keyword}'."
        present = _keyword_present(keyword, parsed_doc)
        actual = 'Required field found' if present else 'Required field missing'
        confidence = 1.0 if present else 0.0
        explanation = f"Fallback keyword check for '{keyword}'."
        passed = present
        reason_code = 'FALLBACK_KEYWORD_FOUND' if present else 'FALLBACK_KEYWORD_MISSING'
        if use_llm:
            rule_for_llm = {'rule_type': 'keyword', 'rule_spec': {'keyword': keyword}, 'confidence_threshold': conf_thresh}
            llm = _apply_llm_review(rule_for_llm, parsed_doc, llm_model)
            llm_outcome = llm['llm_outcome']
            llm_confidence = llm['llm_confidence']
            llm_explanation = llm['llm_explanation']
            llm_evidence = llm['llm_evidence']
            llm_missing_info = llm['llm_missing_info']
            llm_recommendation = llm['llm_recommendation']
            llm_error = llm['llm_error']
            confidence = max(confidence, llm_confidence)
            if llm_outcome == 'FAIL':
                passed = False
            elif llm_outcome == 'PASS':
                passed = True
            explanation += f" | LLM: {llm_explanation}"

    # Determine final score with LLM outcome as authoritative
    if llm_outcome == 'FAIL':
        score = 0
        status = 'FAIL'
    elif llm_outcome == 'PARTIAL':
        score = 50
        status = 'PARTIAL'
    else:
        # Fall back to heuristic/confidence when LLM outcome is PASS/None
        if not passed:
            score = 0
            status = 'FAIL'
        elif confidence >= conf_thresh:
            score = 100
            status = 'PASS'
        elif confidence >= 0.5:
            score = 50
            status = 'PARTIAL'
        else:
            score = 0
            status = 'FAIL'

    if llm_error:
        logger.warning(
            "Rule scored with LLM error fallback | type=%s | status=%s | score=%s | reason=%s",
            rtype,
            status,
            score,
            reason_code,
        )
    else:
        logger.info(
            "Rule evaluated | type=%s | status=%s | score=%s | passed=%s | reason=%s | llm=%s",
            rtype,
            status,
            score,
            passed,
            reason_code,
            llm_outcome or "n/a",
        )

    return {
        'pass': passed,
        'status': status,
        'confidence': confidence,
        'score': score,
        'explanation': explanation,
        'expected': expected,
        'actual': actual,
        'reason_code': reason_code,
        'llm_outcome': llm_outcome,
        'llm_confidence': llm_confidence,
        'llm_explanation': llm_explanation,
        'llm_evidence': llm_evidence,
        'llm_missing_info': llm_missing_info,
        'llm_recommendation': llm_recommendation,
        'llm_error': llm_error,
    }
