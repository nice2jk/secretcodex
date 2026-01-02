const CACHE_NAME = 'trash-board-v2'; // 버전을 v2로 올려서 기존 캐시를 무효화합니다.
const urlsToCache = [
  // '/' (홈)는 여기서 뺍니다! 홈 화면은 캐시하지 않는 게 안전합니다.
  '/static/board/trash-icon.svg',
  // 그 외 변하지 않는 아이콘이나 CSS 파일만 넣으세요.
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
  self.skipWaiting(); // 새로운 서비스 워커가 즉시 적용되게 함
});

self.addEventListener('fetch', event => {
  // 1. 홈 화면(/)이나 데이터 관련 요청은 무조건 네트워크 우선!
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  // 2. 나머지는 캐시 확인 후 네트워크 연결
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});