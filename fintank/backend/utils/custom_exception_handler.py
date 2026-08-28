from rest_framework.views import exception_handler

def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # Now add the HTTP status code to the response.

    # Gets access to exception class that occurs

    exception_class = exc.__class__.__name__
    print(exception_class)

    if exception_class == 'AuthenticationFailed':
        response.data = {
            "error":"Invalid email or password, please try again"
        }

    if exception_class == 'NotAuthenticated':
        response.data = {
            "error":"You Are not authenticated, Please log in to access your resources."
        }

    if exception_class == 'InvalidToken':
        response.data = {
            "error":"Your Token Has expired, please log in again to view your resources."
        }

    # if response is not None:
    #     response.data['status_code'] = response.status_code

    return response