import base64
import hashlib
import json
import requests
import time
from core.config import settings

class PhonePeClient:
    _cached_token = None
    _token_expiry = 0

    def __init__(self):
        self.mid = settings.PHONEPE_MID
        self.salt_key = settings.PHONEPE_SALT_KEY
        self.salt_index = settings.PHONEPE_SALT_INDEX
        self.base_url = settings.PHONEPE_BASE_URL
        self.redirect_url = settings.PHONEPE_REDIRECT_URL
        self.callback_url = settings.PHONEPE_CALLBACK_URL
        
        # V2 OAuth Credentials
        self.client_id = settings.PHONEPE_CLIENT_ID
        self.client_secret = settings.PHONEPE_CLIENT_SECRET

    def _is_v2(self) -> bool:
        # If we have Client ID and Secret, we use the V2 Checkout flows
        return bool(self.client_id and self.client_secret)

    def _get_access_token(self) -> str:
        # Check if we already have a valid cached token
        if PhonePeClient._cached_token and time.time() < PhonePeClient._token_expiry - 60:
            return PhonePeClient._cached_token

        # Otherwise fetch a new token
        url = "https://api.phonepe.com/apis/identity-manager/v1/oauth/token"
        if "api-preprod" in self.base_url or "sandbox" in self.base_url:
            url = "https://api-preprod.phonepe.com/apis/identity-manager/v1/oauth/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "client_version": "1"
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "accept": "application/json"
        }
        
        response = requests.post(url, data=data, headers=headers, timeout=15)
        response.raise_for_status()
        res_json = response.json()
        
        PhonePeClient._cached_token = res_json["access_token"]
        PhonePeClient._token_expiry = time.time() + res_json.get("expires_in", 3600)
        return PhonePeClient._cached_token

    def _generate_checksum(self, payload_string: str, endpoint: str) -> str:
        data_to_hash = f"{payload_string}{endpoint}{self.salt_key}"
        sha256_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        return f"{sha256_hash}###{self.salt_index}"

    def initiate_payment(self, transaction_id: str, amount_in_rupees: float, user_id: str) -> dict:
        if self._is_v2():
            return self._initiate_payment_v2(transaction_id, amount_in_rupees)
        else:
            return self._initiate_payment_v1(transaction_id, amount_in_rupees, user_id)

    def _initiate_payment_v1(self, transaction_id: str, amount_in_rupees: float, user_id: str) -> dict:
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
        response = requests.post(url, json={"request": base64_payload}, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def _initiate_payment_v2(self, transaction_id: str, amount_in_rupees: float) -> dict:
        token = self._get_access_token()
        amount_in_paise = int(amount_in_rupees * 100)
        
        # Dynamically map V2 base URL (standard checkout V2 PG base is /apis/pg instead of /apis/hermes)
        base = self.base_url
        if "hermes" in base:
            base = base.replace("hermes", "pg")
            
        url = f"{base}/checkout/v2/pay"
        
        payload = {
            "merchantOrderId": transaction_id,
            "amount": amount_in_paise,
            "expireAfter": 1200,
            "paymentFlow": {
                "type": "PG_CHECKOUT",
                "merchantUrls": {
                    "redirectUrl": self.redirect_url
                }
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"O-Bearer {token}",
            "accept": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        res_json = response.json()
        
        # Map V2 response structure back to V1 structure for compatibility with billing.py
        return {
            "success": True,
            "code": "SUCCESS",
            "message": "Payment initiated successfully",
            "data": {
                "instrumentResponse": {
                    "redirectInfo": {
                        "url": res_json["redirectUrl"]
                    }
                }
            }
        }

    def check_status(self, transaction_id: str) -> dict:
        if self._is_v2():
            return self._check_status_v2(transaction_id)
        else:
            return self._check_status_v1(transaction_id)

    def _check_status_v1(self, transaction_id: str) -> dict:
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

    def _check_status_v2(self, transaction_id: str) -> dict:
        token = self._get_access_token()
        
        base = self.base_url
        if "hermes" in base:
            base = base.replace("hermes", "pg")
            
        url = f"{base}/checkout/v2/order/{transaction_id}/status"
        
        headers = {
            "Authorization": f"O-Bearer {token}",
            "accept": "application/json"
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        res_json = response.json()
        
        state = res_json.get("state")
        v1_code = "PAYMENT_PENDING"
        if state == "COMPLETED":
            v1_code = "PAYMENT_SUCCESS"
        elif state == "FAILED":
            v1_code = "PAYMENT_ERROR"
            
        # Map V2 status response back to V1 structure for compatibility with billing.py
        return {
            "success": True,
            "code": v1_code,
            "message": "Transaction verified successfully",
            "data": {
                "merchantId": self.mid,
                "merchantTransactionId": transaction_id,
                "transactionId": res_json.get("transactionId") or res_json.get("orderId"),
                "amount": res_json.get("amount", 0),
                "responseCode": v1_code,
                "paymentInstrument": res_json.get("paymentInstrument", {"type": "PG_CHECKOUT"})
            }
        }

    def verify_callback_signature(self, base64_response: str, x_verify_header: str) -> bool:
        # V2 callbacks are verified identical to V1
        data_to_hash = f"{base64_response}{self.salt_key}"
        sha256_hash = hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()
        expected_signature = f"{sha256_hash}###{self.salt_index}"
        return expected_signature == x_verify_header

    def decode_callback_payload(self, base64_response: str) -> dict:
        decoded_bytes = base64.b64decode(base64_response)
        data = json.loads(decoded_bytes.decode('utf-8'))
        
        # If it is a V2 callback payload, map it to look like V1 for compatibility with billing.py
        if "state" in data and "data" not in data:
            state = data.get("state")
            v1_code = "PAYMENT_PENDING"
            if state == "COMPLETED":
                v1_code = "PAYMENT_SUCCESS"
            elif state == "FAILED":
                v1_code = "PAYMENT_ERROR"
                
            return {
                "success": True,
                "code": v1_code,
                "data": {
                    "merchantId": data.get("merchantId"),
                    "merchantTransactionId": data.get("merchantOrderId"),
                    "transactionId": data.get("transactionId") or data.get("orderId"),
                    "amount": data.get("amount"),
                    "paymentInstrument": data.get("paymentInstrument", {})
                }
            }
            
        return data
