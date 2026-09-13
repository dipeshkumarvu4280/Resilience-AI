import asyncio 
from app.services.sms_provider import get_sms_provider 
 
async def test(): 
    provider = get_sms_provider() 
    print("\n--- PROVIDER CONFIG ---") 
    print("Provider Class:", type(provider).__name__) 
    print("Mode          :", getattr(provider, "mode", "N/A")) 
    print("Configured?   :", provider.is_configured()) 
 
    test_number = "+919801338643"  # Apna verified number dalein 
 
    print(f"\nSending test custom SMS to {test_number}...") 
    result = await provider.send_sms( 
        recipient_phone=test_number, 
        message="Critical Emergency Alert: Test message from Resilience System" 
    ) 
 
    print("\n--- DELIVERY RESULT ---") 
    print("Status      :", result.status) 
    print("Message SID :", result.provider_message_id) 
    print("Error Code  :", result.error_code) 
    print("Error Msg   :", result.error_message) 
 
if __name__ == "__main__": 
    asyncio.run(test()) 
