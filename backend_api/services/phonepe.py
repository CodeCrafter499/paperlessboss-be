import base64
import hashlib
import json
import requests
from core.config import settings

class PhonePeClient:
    def __init__(self):
        self.mid = settings.PHONEPE_MID
        self.salt_key = settings.PHONEPE_SALT_KEY
        self.salt_index = settings.PHONEPE_SALT_INDEX
        self.base_url = settings.PHONEPE_BASE_URL
        self.redirect_url = settings.PHONEPE_REDIRECT_URL
        self.callback_url = settings.PHONEPE_CALLBACK_URL

    def _generate_checksum(self, payload_string: str, endpoint: str) -> str:
        data_to_hash = f"{payload_string}{endpoint}{self.salt_key}"
        sha256_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        return f"{sha256_hash}###{self.salt_index}"

    def initiate_payment(self, transaction_id: str, amount_in_rupees: float, user_id: str) -> dict:
        amount_in_paise = int(amount_in_rupees * 100)
        
        payload = {
            "merchantId": self.mid,
            "merchantTransactionId": transaction_id,
            "merchantUserId": user_id,
            "amount": amount_in_paise,
            "redirectUrl": self.redirect_url,
            "redirectMode": "REDIRECT",
            "callbackUrl": self.callback_url,
            "paymentInstrument": {
                "type": "PAY_PAGE"
            }
        }
        
        json_payload = json.dumps(payload)
        base64_payload = base64.b64encode(json_payload.encode('utf-8')).decode('utf-8')
        
        x_verify = self._generate_checksum(base64_payload, "/pg/v1/pay")
        
        headers = {
            "Content-Type": "application/json",
            "X-VERIFY": x_verify,
            "accept": "application/json"
        }
        
        url = f"{self.base_url}/pg/v1/pay"
        try:
            response = requests.post(url, json={"request": base64_payload}, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            try:
                error_detail = response.json()
                raise Exception(f"PhonePe API returned error: {error_detail.get('message', '')} (Code: {error_detail.get('code', '')})") from e
            except Exception:
                raise Exception(f"PhonePe API failed with status {response.status_code}: {response.text}") from e

    def check_status(self, transaction_id: str) -> dict:
        endpoint = f"/pg/v1/status/{self.mid}/{transaction_id}"
        
        data_to_hash = f"{endpoint}{self.salt_key}"
        sha256_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        x_verify = f"{sha256_hash}###{self.salt_index}"
        
        headers = {
            "Content-Type": "application/json",
            "X-VERIFY": x_verify,
            "X-MERCHANT-ID": self.mid,
            "accept": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def verify_callback_signature(self, base64_response: str, x_verify_header: str) -> bool:
        data_to_hash = f"{base64_response}{self.salt_key}"
        sha256_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        expected_signature = f"{sha256_hash}###{self.salt_index}"
        return expected_signature == x_verify_header

    def decode_callback_payload(self, base64_response: str) -> dict:
        decoded_bytes = base64.b64decode(base64_response)
        return json.loads(decoded_bytes.decode('utf-8'))
