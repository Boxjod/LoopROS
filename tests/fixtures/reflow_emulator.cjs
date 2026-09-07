// Test-only real terminal reflow engine; dependency supplied outside the project.
const {Terminal} = require(process.env.XTERM_HEADLESS_MODULE);
const terminal = new Terminal({cols:100, rows:30, scrollback:5000, allowProposedApi:true});
let replies = [];
terminal.onData(data => replies.push(data));
let pending = Promise.resolve();
require('readline').createInterface({input:process.stdin}).on('line', line => {
  pending = pending.then(async () => {
    const request = JSON.parse(line);
    if (request.resize) terminal.resize(request.resize[1], request.resize[0]);
    if (request.text) await new Promise(resolve => terminal.write(request.text, resolve));
    const buffer = terminal.buffer.active;
    const all = Array.from({length:buffer.length}, (_,i) => buffer.getLine(i).translateToString(false));
    process.stdout.write(JSON.stringify({display:all.slice(buffer.viewportY,buffer.viewportY+30), history:all.slice(0,buffer.viewportY), replies})+'\n');
    replies = [];
  });
});
