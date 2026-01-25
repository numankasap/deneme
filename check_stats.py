"""
Soru bankası istatistiklerini kontrol et ve progress tablosunu temizle
"""
import os

# Supabase import
try:
    from supabase import create_client, Client
except ImportError:
    from supabase._sync.client import SyncClient as Client
    from supabase import create_client

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print('=' * 60)
print('📊 SORU BANKASI İSTATİSTİKLERİ')
print('=' * 60)

# Toplam soru sayısı (Matematik ve Geometri)
total = supabase.table('question_bank').select('id', count='exact').in_('subject', ['Matematik', 'Geometri']).execute()
print(f'\n📚 Toplam Matematik/Geometri sorusu: {total.count}')

# Görselli soru sayısı
gorselli_result = supabase.table('question_bank').select('id', count='exact').in_('subject', ['Matematik', 'Geometri']).not_.is_('image_url', 'null').execute()
print(f'🖼️  Görselli sorular: {gorselli_result.count}')

# Görselsiz soru sayısı
gorselsiz_result = supabase.table('question_bank').select('id', count='exact').in_('subject', ['Matematik', 'Geometri']).is_('image_url', 'null').execute()
print(f'📝 Görselsiz sorular: {gorselsiz_result.count}')

# Verified durumu
verified_true = supabase.table('question_bank').select('id', count='exact').in_('subject', ['Matematik', 'Geometri']).eq('verified', True).execute()
verified_null = supabase.table('question_bank').select('id', count='exact').in_('subject', ['Matematik', 'Geometri']).is_('verified', 'null').execute()

print(f'\n✅ Verified TRUE: {verified_true.count}')
print(f'⏳ Verified NULL: {verified_null.count}')

# Progress tablosu durumu
try:
    progress = supabase.table('question_improver_progress').select('status', count='exact').execute()
    print(f'\n📋 Progress tablosunda: {progress.count} kayıt')

    success = supabase.table('question_improver_progress').select('question_id', count='exact').eq('status', 'success').execute()
    failed = supabase.table('question_improver_progress').select('question_id', count='exact').eq('status', 'failed').execute()
    print(f'   - Success: {success.count}')
    print(f'   - Failed: {failed.count}')
except Exception as e:
    print(f'\n📋 Progress tablosu hatası: {e}')

print('\n' + '=' * 60)
print('\n🔧 BAŞTAN BAŞLAMAK İÇİN:')
print('   1. Progress tablosunu temizle (DELETE FROM question_improver_progress)')
print('   2. Verified sütununu NULL yap (UPDATE question_bank SET verified = NULL)')
print('=' * 60)
