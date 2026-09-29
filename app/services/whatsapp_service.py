import re
import random
from datetime import datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    GoogleMapsLead,
    WhatsAppAutoResponder,
    WhatsAppBulkJob,
    WhatsAppGroupTask,
    User,
)
from app.services.security import tenant_id_for_user


def resolve_spintax(text: str) -> str:
    """
    Parses and resolves spintax variations like {Hello|Hi|Greetings}.
    Ignores dynamic double-brace variables like {{name}}.
    """
    pattern = re.compile(r"(?<!\{)\{([^{}]+?\|[^{}]+?)\}(?!\})")
    while pattern.search(text):
        text = pattern.sub(lambda m: random.choice(m.group(1).split("|")), text)
    return text


def personalize_message(template: str, recipient: dict[str, Any]) -> str:
    """
    Replaces dynamic tokens like {{name}}, {{phone}}, {{city}}, {{segment}}, {{total_spent}}
    and resolves spintax variations.
    """
    resolved = resolve_spintax(template or "")
    
    name = recipient.get("name") or "Valued Customer"
    phone = recipient.get("phone") or ""
    email = recipient.get("email") or ""
    
    lifecycle = recipient.get("lifecycle") or {}
    demographics = recipient.get("demographics") or {}
    
    segment = lifecycle.get("segment") or "general"
    city = demographics.get("city") or recipient.get("city") or "your area"
    total_spent = str(lifecycle.get("totalSpent") or 0)
    
    replacements = {
        r"\{\{\s*name\s*\}\}": name,
        r"\{\{\s*customer_name\s*\}\}": name,
        r"\{\{\s*phone\s*\}\}": phone,
        r"\{\{\s*email\s*\}\}": email,
        r"\{\{\s*segment\s*\}\}": segment,
        r"\{\{\s*city\s*\}\}": city,
        r"\{\{\s*total_spent\s*\}\}": total_spent,
    }
    
    for pat, val in replacements.items():
        resolved = re.sub(pat, str(val), resolved, flags=re.IGNORECASE)
        
    return resolved


def filter_phone_numbers(
    raw_numbers: list[str] | str, default_country_code: str = "+91"
) -> dict[str, Any]:
    """
    Filters, sanitizes, and deduplicates phone numbers.
    Separates into valid, invalid, and duplicate lists.
    """
    if isinstance(raw_numbers, str):
        lines = re.split(r"[\r\n,;]+", raw_numbers)
    else:
        lines = raw_numbers

    cleaned_default_prefix = re.sub(r"\D", "", default_country_code) or "91"

    valid_list = []
    invalid_list = []
    duplicate_list = []
    seen = set()

    for item in lines:
        raw = str(item or "").strip()
        if not raw:
            continue

        digits_only = re.sub(r"\D", "", raw)
        if not digits_only:
            invalid_list.append({"original": raw, "reason": "No digits found"})
            continue

        # If starts with '0', remove leading zero
        if digits_only.startswith("0") and len(digits_only) > 9:
            digits_only = digits_only[1:]

        formatted_number = None

        # Format detection
        if len(digits_only) == 10:
            formatted_number = f"+{cleaned_default_prefix}{digits_only}"
        elif len(digits_only) == 12 and digits_only.startswith(cleaned_default_prefix):
            formatted_number = f"+{digits_only}"
        elif len(digits_only) == 11 and digits_only.startswith("1"):  # US/Canada
            formatted_number = f"+{digits_only}"
        elif 10 <= len(digits_only) <= 15:
            formatted_number = f"+{digits_only}"
        else:
            invalid_list.append({"original": raw, "reason": f"Invalid length ({len(digits_only)} digits)"})
            continue

        if formatted_number in seen:
            duplicate_list.append({"original": raw, "formatted": formatted_number})
        else:
            seen.add(formatted_number)
            valid_list.append({
                "original": raw,
                "formatted": formatted_number,
                "country_code": "+" + cleaned_default_prefix,
                "whatsapp_ready": True,
            })

    return {
        "summary": {
            "total_input": len(lines),
            "valid_count": len(valid_list),
            "invalid_count": len(invalid_list),
            "duplicate_count": len(duplicate_list),
        },
        "valid": valid_list,
        "invalid": invalid_list,
        "duplicates": duplicate_list,
    }


def parse_group_links(raw_links: list[str] | str) -> list[dict[str, Any]]:
    """
    Parses WhatsApp group invite links like https://chat.whatsapp.com/L123abc456
    """
    if isinstance(raw_links, str):
        lines = re.split(r"[\r\n,;]+", raw_links)
    else:
        lines = raw_links

    pattern = re.compile(r"chat\.whatsapp\.com/(?:invite/)?([a-zA-Z0-9_-]{20,24})")
    results = []
    seen = set()

    for item in lines:
        text = str(item or "").strip()
        if not text:
            continue
        match = pattern.search(text)
        if match:
            code = match.group(1)
            is_dup = code in seen
            seen.add(code)
            results.append({
                "original_url": text,
                "invite_code": code,
                "is_valid": True,
                "is_duplicate": is_dup,
                "status": "ready",
            })
        else:
            results.append({
                "original_url": text,
                "invite_code": None,
                "is_valid": False,
                "is_duplicate": False,
                "status": "invalid_link",
            })

    return results


def grab_members_from_text(raw_text: str, default_country_code: str = "+91") -> list[dict[str, Any]]:
    """
    Extracts phone numbers and names from pasted group participant logs or WhatsApp chats.
    """
    cleaned_default_prefix = re.sub(r"\D", "", default_country_code) or "91"
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    extracted = []
    seen_phones = set()

    # Pattern for international or local phone numbers
    phone_pattern = re.compile(r"(?:\+?\d{1,4}[ -]?)?(?:\(?\d{2,5}\)?[ -]?)?\d{3,5}[ -]?\d{3,5}")

    for line in lines:
        matches = phone_pattern.findall(line)
        for match in matches:
            digits = re.sub(r"\D", "", match)
            if len(digits) >= 10:
                if len(digits) == 10:
                    formatted = f"+{cleaned_default_prefix}{digits}"
                elif len(digits) == 12 and digits.startswith(cleaned_default_prefix):
                    formatted = f"+{digits}"
                else:
                    formatted = f"+{digits}"

                if formatted not in seen_phones:
                    seen_phones.add(formatted)
                    
                    # Try to extract potential name if line has text before the number
                    potential_name = line.replace(match, "").strip(" -:,~\"'()")
                    if not potential_name or len(potential_name) > 50:
                        potential_name = f"Member {formatted[-4:]}"

                    extracted.append({
                        "name": potential_name,
                        "phone": formatted,
                        "raw_match": match,
                    })

    return extracted


def evaluate_auto_responder(
    db: Session,
    user: User,
    incoming_message: str,
    sender_phone: str | None = None,
) -> dict[str, Any]:
    """
    Evaluates incoming WhatsApp message against active auto responder rules for tenant.
    """
    msg_clean = (incoming_message or "").strip().lower()
    t_id = tenant_id_for_user(user)

    rules = db.scalars(
        select(WhatsAppAutoResponder)
        .where(
            WhatsAppAutoResponder.tenant_id == t_id,
            WhatsAppAutoResponder.organization_id == user.organization_id,
            WhatsAppAutoResponder.is_active == True,  # noqa: E712
        )
        .order_by(WhatsAppAutoResponder.priority.desc(), WhatsAppAutoResponder.created_at.asc())
    ).all()

    matched_rule = None
    default_fallback_rule = None

    for rule in rules:
        if rule.trigger_type == "default_fallback":
            default_fallback_rule = rule
            continue

        keywords = [k.strip().lower() for k in (rule.keywords or []) if k.strip()]
        
        if rule.trigger_type == "exact":
            if any(msg_clean == kw for kw in keywords):
                matched_rule = rule
                break
        elif rule.trigger_type == "contains":
            if any(kw in msg_clean for kw in keywords):
                matched_rule = rule
                break
        elif rule.trigger_type == "starts_with":
            if any(msg_clean.startswith(kw) for kw in keywords):
                matched_rule = rule
                break
        elif rule.trigger_type == "regex":
            for kw in keywords:
                try:
                    if re.search(kw, msg_clean):
                        matched_rule = rule
                        break
                except re.error:
                    pass
            if matched_rule:
                break

    selected_rule = matched_rule or default_fallback_rule

    if not selected_rule:
        return {
            "matched": False,
            "message": "No matching auto-responder rule found.",
            "response": None,
        }

    # Increment match statistics
    selected_rule.match_count = (selected_rule.match_count or 0) + 1
    selected_rule.last_triggered_at = datetime.utcnow()
    db.commit()

    recipient_context = {
        "name": "Customer",
        "phone": sender_phone or "",
    }
    
    # Try looking up customer details by phone if available
    if sender_phone:
        customer = db.scalar(
            select(Customer).where(
                Customer.tenant_id == t_id,
                Customer.organization_id == user.organization_id,
                Customer.phone == sender_phone,
            )
        )
        if customer:
            recipient_context["name"] = customer.name
            recipient_context["lifecycle"] = customer.lifecycle or {}
            recipient_context["demographics"] = customer.demographics or {}

    response_text = personalize_message(selected_rule.response_message, recipient_context)

    return {
        "matched": True,
        "rule_id": selected_rule.id,
        "rule_name": selected_rule.name,
        "trigger_type": selected_rule.trigger_type,
        "response_message": response_text,
        "buttons": selected_rule.buttons or [],
        "media_files": selected_rule.media_files or [],
    }
