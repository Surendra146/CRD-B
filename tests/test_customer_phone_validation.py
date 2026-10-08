import pytest
from pydantic import ValidationError

from app.schemas.customer import CustomerCreateRequest, CustomerUpdateRequest


@pytest.mark.parametrize('phone', ['123456789', '12345678901', 'abcdefghij', '+919876543210', '98765 43210', '', None, '\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\uff10'])
@pytest.mark.parametrize('schema', [CustomerCreateRequest, CustomerUpdateRequest])
def test_customer_phone_rejects_invalid_values(schema, phone):
    payload = dict(externalId='C1', name='Customer', address='Pune', customerCreatedDate='2026-10-08', phone=phone)
    with pytest.raises(ValidationError):
        schema(**payload)


@pytest.mark.parametrize('phone', ['9876543210', '0123456789'])
def test_customer_phone_accepts_ten_digits(phone):
    assert CustomerUpdateRequest(phone=phone).phone == phone
    assert CustomerCreateRequest(externalId='C1', name='Customer', address='Pune', customerCreatedDate='2026-10-08', phone=phone).phone == phone


def test_partial_customer_update_can_omit_phone():
    assert CustomerUpdateRequest(name='Updated').to_payload() == {'name': 'Updated'}
