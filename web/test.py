import requests
import json
url = 'http://192.168.2.2:3222/v1/chat/completions'

headers = {
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Authorization': 'Bearer sk-3Z0EpKrHVDukLuTLFcBbB50735214115Aa40367f3048F796',
    'Cache-Control': 'no-cache',
    'Content-Type': 'application/json',
    'Cookie': 'token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjFhNjdhZmMzLTE0ZjktNGFlMi1iYjE1LWRiODNiOTRjNDdjZCJ9.KRL7VNxi3u4TA-R3tvD2NYZ20iRVX0oSh2GPZH3TK50',
    'Origin': 'http://ltm.zapto.org:1984',
    'Pragma': 'no-cache',
    'Proxy-Connection': 'keep-alive',
    'Referer': 'http://ltm.zapto.org:1984/c/e17411b1-2894-4838-a55d-c8a2d9b7b5d2',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
}

data = {
    "stream": False,
    "model": "qwen-plus",
    "messages": [
        {
            "role": "system",
            "content": """
-Target activity-
You are an intelligent assistant that helps a human analyst to analyze claims against certain entities presented in a text document.

-Goal-
Given a text document that is potentially relevant to this activity, an entity specification, and a claim description, extract all entities that match the entity specification and all claims against those entities.

-Steps-
1. Extract all named entities that match the predefined entity specification. Entity specification can either be a list of entity names or a list of entity types.
2. For each entity identified in step 1, extract all claims associated with the entity. Claims need to match the specified claim description, and the entity should be the subject of the claim.
For each claim, extract the following information:
- Subject: name of the entity that is subject of the claim, capitalized. The subject entity is one that committed the action described in the claim. Subject needs to be one of the named entities identified in step 1.
- Object: name of the entity that is object of the claim, capitalized. The object entity is one that either reports/handles or is affected by the action described in the claim. If object entity is unknown, use **NONE**.
- Claim Type: overall category of the claim, capitalized. Name it in a way that can be repeated across multiple text inputs, so that similar claims share the same claim type
- Claim Status: **TRUE**, **FALSE**, or **SUSPECTED**. TRUE means the claim is confirmed, FALSE means the claim is found to be False, SUSPECTED means the claim is not verified.
- Claim Description: Detailed description explaining the reasoning behind the claim, together with all the related evidence and references.
- Claim Date: Period (start_date, end_date) when the claim was made. Both start_date and end_date should be in ISO-8601 format. If the claim was made on a single date rather than a date range, set the same date for both start_date and end_date. If date is unknown, return **NONE**.
- Claim Source Text: List of **all** quotes from the original text that are relevant to the claim.
- Claim Contact Details Text: (e.g., phone, email, website, address)

Format each claim as (<subject_entity>{tuple_delimiter}<object_entity>{tuple_delimiter}<claim_type>{tuple_delimiter}<claim_status>{tuple_delimiter}<claim_start_date>{tuple_delimiter}<claim_end_date>{tuple_delimiter}<claim_description>{tuple_delimiter}<claim_source>{tuple_delimiter}<claim_contact_details>)

3. Return output in English as a single list of all the claims identified in steps 1 and 2. Use **{record_delimiter}** as the list delimiter.

4. When finished, output {completion_delimiter}

-Examples-
Example 1:
Entity specification: organization
Claim description: red flags associated with an entity
Text: According to an article on 2022/01/10, Company A was fined for bid rigging while participating in multiple public tenders published by Government Agency B. The company is owned by Person C who was suspected of engaging in corruption activities in 2015.
Output:

(COMPANY A{tuple_delimiter}GOVERNMENT AGENCY B{tuple_delimiter}ANTI-COMPETITIVE PRACTICES{tuple_delimiter}TRUE{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}Company A was found to engage in anti-competitive practices because it was fined for bid rigging in multiple public tenders published by Government Agency B according to an article published on 2022/01/10{tuple_delimiter}According to an article published on 2022/01/10, Company A was fined for bid rigging while participating in multiple public tenders published by Government Agency B.)
{completion_delimiter}

Example 2:
Entity specification: Company A, Person C
Claim description: red flags associated with an entity
Text: According to an article on 2022/01/10, Company A was fined for bid rigging while participating in multiple public tenders published by Government Agency B. The company is owned by Person C who was suspected of engaging in corruption activities in 2015.
Output:

(COMPANY A{tuple_delimiter}GOVERNMENT AGENCY B{tuple_delimiter}ANTI-COMPETITIVE PRACTICES{tuple_delimiter}TRUE{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}Company A was found to engage in anti-competitive practices because it was fined for bid rigging in multiple public tenders published by Government Agency B according to an article published on 2022/01/10{tuple_delimiter}According to an article published on 2022/01/10, Company A was fined for bid rigging while participating in multiple public tenders published by Government Agency B.)
{record_delimiter}
(PERSON C{tuple_delimiter}NONE{tuple_delimiter}CORRUPTION{tuple_delimiter}SUSPECTED{tuple_delimiter}2015-01-01T00:00:00{tuple_delimiter}2015-12-30T00:00:00{tuple_delimiter}Person C was suspected of engaging in corruption activities in 2015{tuple_delimiter}The company is owned by Person C who was suspected of engaging in corruption activities in 2015)
{completion_delimiter}

Example 3:
Entity specification: organization
Claim description: red flags associated with an entity
Text: Company A was fined on January 10, 2022, for bid rigging in multiple government project tenders. The company's email is info@companya.com, and the phone number is (123) 456-7890.
Output:

(COMPANY A{tuple_delimiter}NONE{tuple_delimiter}EMAIL{tuple_delimiter}TRUE{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}Company A's email address is info@companya.com{tuple_delimiter}Company A's email address is info@companya.com.)
{record_delimiter}
(COMPANY A{tuple_delimiter}NONE{tuple_delimiter}PHONE{tuple_delimiter}SUSPECTED{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}2022-01-10T00:00:00{tuple_delimiter}Company A's phone number was reported as (123) 456-7890, though it is not confirmed whether it is still valid{tuple_delimiter}Company A's phone number was reported as (123) 456-7890.)
{completion_delimiter}

-Real Data-
Use the following input for your answer.
Entity specification: {entity_specs}
Claim description: {claim_description}
Text: {input_text}
Output:"""
        },
        {
            "role": "user",
            "content": """ 联系我们


稳健平安医疗科技（湖南）有限公司
================



办公电话：[0736\-3242188](tel:0736-3242188)


销售电话：[0736\-3127498](tel:0736-3127498)


邮箱：[hnpamd@163\.com](mailto:hnpamd@163.com)


地址：湖南省澧县经济开发区工业大道8号
"""
        }
    ],
    "session_id": "ggs5b_AAcvZ5rdyhAAEk",
    "chat_id": "e17411b1-2894-4838-a55d-c8a2d9b7b5d2",
    "id": "bc6b1e06-d85b-4d41-938f-df136b9b2e8f"
}

response = requests.post(url, headers=headers, json=data)

# Print the response from the server
print( "请求信息:\n" + json.dumps(response.json(), indent=4, ensure_ascii=False))
