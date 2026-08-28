from django.http import JsonResponse

# Overrides 500 and 404 errors

def handler500(request):
    message = ('Internal Server Error')
    response = JsonResponse(data={'error':message})
    response.status_code = 500
    return response


def handler404(request, exception):
    message = ('Bad Request, route not found')
    response = JsonResponse(data={'error':message})
    response.status_code = 404
    return response