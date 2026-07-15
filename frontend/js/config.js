const isLocalHost = window.location.hostname === 'localhost' || 
                    window.location.hostname === '127.0.0.1' || 
                    window.location.hostname === '' ||
                    window.location.protocol === 'file:' ||
                    window.location.hostname.startsWith('192.168.') || 
                    window.location.hostname.startsWith('10.') || 
                    window.location.hostname.startsWith('172.');

const API_BASE_URL = isLocalHost
    ? `http://${window.location.hostname || '127.0.0.1'}:5000`
    : 'https://leetcode-classroom-tracker-402e.onrender.com';
