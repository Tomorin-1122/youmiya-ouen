export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let path = url.pathname;
    
    if (path === '/') path = '/gallery.html';
    
    const response = await env.ASSETS.fetch(new Request(url.origin + path));
    
    if (response.status === 404) {
      return new Response('Not Found', { status: 404 });
    }
    
    return response;
  }
};
