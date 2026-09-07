const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

for (const lang of ['en', 'zh-CN']) test(lang + ' platform selection, terminal-only commands and clipboard fallback', async () => {
  const make = () => ({textContent:'', checked:false, disabled:false, events:{}, attrs:{},
    addEventListener(name, fn){this.events[name]=fn;}, setAttribute(name,value){this.attrs[name]=value;}});
  const ids = Object.fromEntries(['command','light','copy-status','platform-note','copy'].map(id=>[id,make()]));
  const buttons = ['linux','mac','windows','legacy','cmd'].map(platform=>Object.assign(make(),{dataset:{platform}}));
  let copied, selected = false;
  const context = {document:{documentElement:{lang}, getElementById:id=>ids[id], querySelectorAll:()=>buttons,
    createRange:()=>({selectNodeContents(){selected=true;}})},
    navigator:{clipboard:{async writeText(value){copied=value;}}},
    window:{getSelection:()=>({removeAllRanges(){},addRange(){}})}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../website/site.js'),'utf8'),context);
  assert.equal(ids.command.textContent,'curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh');
  buttons[2].events.click();
  assert.match(ids.command.textContent,/install.ps1$/);
  ids.light.checked = true; ids.light.events.change();
  assert.match(ids.command.textContent,/--terminal-only$/);
  await ids.copy.events.click(); assert.equal(copied,ids.command.textContent);
  assert.match(ids['copy-status'].textContent,lang === 'zh-CN' ? /已复制/ : /copied/);
  buttons[4].events.click(); assert.match(ids.command.textContent,/ && powershell/);
  assert.match(ids.command.textContent,/--terminal-only$/);
  buttons[3].events.click();
  assert.equal(ids.light.disabled,true); assert.match(ids.command.textContent,/^ssh /);
  assert.equal(ids.command.textContent.includes('--terminal-only'),false);
  context.navigator.clipboard.writeText = async()=>{throw Error('blocked');};
  await ids.copy.events.click(); assert.equal(selected,true);
  buttons[1].events.click(); assert.equal(ids.command.textContent,'curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh -s -- --terminal-only');
  assert.equal(ids.light.disabled,false);
  assert.equal(buttons[1].attrs['aria-pressed'],'true');
  ids.light.checked = false; ids.light.events.change();
  assert.equal(ids.command.textContent,'curl -fsSL https://loopmaster.box2ai.com/LoopROS/install.sh | sh');
});
