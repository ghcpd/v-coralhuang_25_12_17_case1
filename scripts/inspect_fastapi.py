import fastapi
from fastapi.openapi.models import Contact
print('Contact __annotations__ =', getattr(Contact, '__annotations__', None))
print('Contact has name attr?', hasattr(Contact, 'name'))
print('Contact dir name in dir:', 'name' in dir(Contact))
print('Contact source repr:', Contact)
