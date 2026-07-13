VALIDATION_RULES = {
    "1. Name of employee": {
        "required": True,
        "type": "regex",
        "pattern": r"^[a-zA-Z\s\.]+$",
        "message": "employee name should contain only alphabets, spaces, and dots"
    },

    "2. Father's/Mother's/Spouse Name": {
        "required": True,
        "type": "regex",
        "pattern": r"^[a-zA-Z\s\.]+$",
        "message": "father/mother/spouse name should contain only alphabets, spaces, and dots"
    },

    "3. Designation": {
        "required": False,
        "type": "designation",
        "message": "designation should contain only alphabets, spaces and special characters"
    },

    "4. UAN": {
        "required": False,
        "type": "numeric_length",
        "length": 12,
        "message": "UAN should be exactly 12 digits only numeric"
    },

    "5. Bank Account Number": {
        "required": False,
        "type": "text",
        "message": ""
    },

    "6a. Wage month": {
        "required": True,
        "type": "text",
        "message": ""
    },

    "6b. Wage Year": {
        "required": True,
        "type": "numeric",
        "message": "wage year should be a numeric value"
    },

    "7a.Rate of Basic": {
        "required": True,
        "type": "numeric",
        "message": "rate of basic should be a numeric value"
    },

    "7b. Rate of DA": {
        "required": False,
        "type": "numeric",
        "message": "rate of DA should be a numeric value"
    },

    "7c. Rate of Allowances": {
        "required": False,
        "type": "numeric",
        "message": "rate of allowances should be a numeric value"
    },

    "8. Total attendance/unit of work done": {
        "required": True,
        "type": "numeric",
        "message": "total attendance should be a numeric value"
    },

    "9. Overtime wages": {
        "required": False,
        "type": "numeric",
        "message": "overtime wages should be a numeric value"
    },

    "10. Gross wages payable": {
        "required": True,
        "type": "numeric",
        "message": "gross wages payable should be a numeric value"
    },

    "11a. PF": {
        "required": False,
        "type": "numeric",
        "message": "PF deduction should be a numeric value"
    },

    "11b. ESI": {
        "required": False,
        "type": "numeric",
        "message": "ESI deduction should be a numeric value"
    },

    "11c. Others": {
        "required": False,
        "type": "numeric",
        "message": "other deductions should be a numeric value"
    },

    "12. Net wages paid": {
        "required": True,
        "type": "numeric",
        "message": "net wages paid should be a numeric value"
    }
}
