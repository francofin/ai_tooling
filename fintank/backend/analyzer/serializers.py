from rest_framework import serializers
from stockuploader.models import Stock,  ETF, ProfileStock, Crypto

class StockSerializer(serializers.ModelSerializer):

    user = serializers.StringRelatedField()
    class Meta:
        model=Stock
        fields = '__all__'

