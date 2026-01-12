import json, os
from baseline_moderation_service import SubmitContentRequest
from policy_engine import evaluate_request
p = {
    'enabled': True,
    'policies': [
        {'id': 'low1', 'match': {'any': [{'type': 'keyword', 'value': 'hello'}]}, 'risk': 'low'}
    ]
}
with open('policy.json', 'w') as f:
    json.dump(p, f)
os.environ['MODERATION_POLICY_FILE'] = os.path.abspath('policy.json')
req = SubmitContentRequest(user_id='u1', text='hello there')
print('eval result:', evaluate_request(req))
