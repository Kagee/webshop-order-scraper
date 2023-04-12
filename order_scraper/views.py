# from django.shortcuts import render
from django.http import HttpResponse


# Create your views here.
def index(request):  # pylint: disable=unused-argument
    return HttpResponse("Hello. This is the scraper index page")
