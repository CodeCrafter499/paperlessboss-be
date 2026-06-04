
VALIDATION_RULES = {

    "Name of employee": {
        "required": True,
        "type": "regex",
        "pattern": r"^[A-Za-z.\s]+$",
        "message": "employee name shouldn't consist special characters except . and space"
    },

    "Date of birth": {
        "required": True,
        "type": "date",
        "format": "%d-%m-%Y",
        "message": "date of birth should be in dd-mm-yyyy format"
    },

    "Father's / Mother's name": {
        "required": True,
        "type": "regex",
        "pattern": r"^[A-Za-z.\s]+$",
        "message": "parent name shouldn't consist special characters except . and space"
    },

    "Aadhaar number": {
        "required": True,
        "type": "numeric_length",
        "length": 12,
        "message": "aadhaar number should be 12 digits only numeric"
    },

    "Labour Identification Number (LIN) of the establishment": {
        "required": True,
        "type": "text",
        "message": ""
    },

    "Universal Account Number (UAN) and / or Insurance Number (ESIC) (if available)": {
        "required": False,
        "type": "numeric_length",
        "length": 12,
        "message": "UAN/ESIC should be 12 digits only numeric"
    },

    "Designation": {
        "required": False,
        "type": "designation",
        "message": "designation should contain only alphabets, spaces and special characters"
    },

    "Type of Employment": {
        "required": False,
        "type": "text",
        "message": ""
    },

    "Category of Skill": {
        "required": False,
        "type": "text",
        "message": ""
    },

    "Date of Joining": {
        "required": False,
        "type": "date",
        "format": "%d-%m-%Y",
        "message": "date of joining should be in dd-mm-yyyy format"
    },

    "Basic Pay": {
        "required": False,
        "type": "numeric",
        "message": "basic pay should be a numeric value"
    },

    "Dearness Allowance": {
        "required": False,
        "type": "numeric",
        "message": "dearness allowance should be a numeric value"
    },

    "Other Allowance": {
        "required": False,
        "type": "numeric",
        "message": "other allowance should be a numeric value"
    },

    "Applicability of social security benefits": {
        "required": False,
        "type": "text",
        "message": ""
    },

    "Broad nature of duties performed": {
        "required": False,
        "type": "word_limit",
        "limit": 100,
        "message": "text should not exceed 100 words"
    },

    "Benefits available under chapter VI (Maternity Benefit) of Code on Social Security, 2020 (in case of women employee)": {
        "required": False,
        "type": "text",
        "message": ""
    },

    "Any other information": {
        "required": False,
        "type": "text",
        "message": ""
    },
}
