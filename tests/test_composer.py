import json
import unittest
from prompt_toolkit.buffer import Buffer
from loop_robot.terminal.composer import Composer


class ComposerTests(unittest.TestCase):
    def make(self):
        files=[];composer=Composer(Buffer(),lambda:files)
        return composer,files

    def test_multiline_preserved_and_two_backspaces_delete_only_chip(self):
        c,_=self.make();c.buffer.insert_text('说明 ');c.paste('  x = 1\n  y = 2\n')
        self.assertEqual(c.text,'说明   x = 1\n  y = 2\n')
        self.assertIn('[Paste #1 · 2 lines]',c.display_text)
        self.assertNotIn('\n',c.buffer.text)
        self.assertTrue(c.backspace());self.assertIn('x = 1',c.text)
        self.assertTrue(c.backspace());self.assertEqual(c.text,'说明 ')

    def test_intervening_edit_disarms_deletion(self):
        c,_=self.make();c.paste('a\nb');c.backspace()
        c.buffer.insert_text('x');c.buffer.delete_before_cursor()
        c.backspace();self.assertEqual(c.text,'a\nb')
        c.backspace();self.assertEqual(c.text,'')

    def test_image_ids_payload_and_restored_draft(self):
        c,files=self.make()
        files.extend([('same.png',[{'type':'image_url','image_url':{'url':'first'}}]),
                      ('same.png',[{'type':'image_url','image_url':{'url':'second'}}])])
        c.ensure_images();c.paste('a\nb')
        self.assertIn('[Image #1][Image #2][Paste #3',c.display_text)
        saved=json.loads(json.dumps(c.snapshot()));new,newfiles=self.make()
        newfiles.extend(json.loads(json.dumps(files)));new.restore(c.text,saved)
        self.assertEqual(c.display_text,new.display_text)
        self.assertEqual(new.numbered_files()[1][1][0]['text'],'[Image #2]')
        new.backspace();new.backspace()  # Paste only.
        new.backspace();self.assertEqual(len(newfiles),2)
        new.backspace();self.assertEqual(len(newfiles),1)
        self.assertEqual(newfiles[0][1][0]['image_url']['url'],'first')
        self.assertIn('[Image #1]',new.display_text)

    def test_reset_preserves_files_for_submission_and_history_is_expanded(self):
        c,files=self.make();files.append(('photo.png',[{'type':'image_url'}]));c.ensure_images();c.paste('a\nb')
        c.reset(history=True)
        self.assertEqual(len(files),1);self.assertEqual(c.buffer.text,'')
        self.assertEqual(c.buffer.history.get_strings(),['a\nb'])
        c.ensure_images();c.clear();self.assertEqual(files,[]);self.assertEqual(c.buffer.text,'')

    def test_queue_refold_retains_image_number_without_duplicate_label(self):
        c,files=self.make();c.paste('a\nb');files.append(('photo.png',[{'type':'image_url'}]));c.ensure_images()
        frozen=c.numbered_files();c.reset();files[:]=frozen;c.restore('a\nb')
        self.assertIn('[Image #2]',c.display_text)
        self.assertEqual(sum(p['type']=='text' for p in c.numbered_files()[0][1]),1)
