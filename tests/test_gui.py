"""Exercise Tk controls and worker callbacks with an invisible application."""
import time
from pathlib import Path
import os
import subprocess
import sys

import pytest

from .fixtures import make_session


@pytest.mark.parametrize('relative_path',['fieldfox_recording/gui.py','scripts/fieldfox_gui.py'])
def test_direct_gui_file_imports_from_another_directory(tmp_path,relative_path):
    import fieldfox_recording
    checkout=Path(fieldfox_recording.__file__).resolve().parents[1]
    script=checkout/relative_path
    code=("import runpy,sys; from pathlib import Path; "
          f"result=runpy.run_path({str(script)!r},run_name='direct_launch_check'); "
          "assert callable(result['main']); "
          "import fieldfox_recording; "
          f"assert Path(fieldfox_recording.__file__).resolve()==Path({str(checkout/'fieldfox_recording/__init__.py')!r}).resolve()")
    result=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,
        env=os.environ|{'PYTHONPATH':''},capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('relative_path',['fieldfox_recording/gui.py','scripts/fieldfox_gui.py'])
def test_direct_gui_file_opens_and_exits_cleanly(tmp_path,relative_path):
    pytest.importorskip('tkinter')
    import fieldfox_recording
    script=Path(fieldfox_recording.__file__).resolve().parents[1]/relative_path
    code="""import runpy,tkinter as tk
original=tk.Tk
def hidden_root():
    root=original()
    root.withdraw()
    root.after(250,root.destroy)
    return root
tk.Tk=hidden_root
"""+f"runpy.run_path({str(script)!r},run_name='__main__')\n"
    result=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,
        env=os.environ|{'PYTHONPATH':''},capture_output=True,text=True,timeout=20)
    if 'no display name' in result.stderr or 'couldn\'t connect to display' in result.stderr:
        pytest.skip('Tk display unavailable')
    assert result.returncode==0,result.stderr


def test_gui_load_plot_and_exports_use_same_selection(tmp_path,monkeypatch):
    tk=pytest.importorskip('tkinter')
    matplotlib=pytest.importorskip('matplotlib');matplotlib.use('Agg')
    io=pytest.importorskip('scipy.io')
    from tkinter import filedialog
    from fieldfox_recording.gui import FieldFoxApp
    try:
        root=tk.Tk();root.withdraw()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    app=FieldFoxApp(root);errors=[]
    monkeypatch.setattr(app,'_error',errors.append)
    def finish():
        deadline=time.monotonic()+30
        while app.busy and time.monotonic()<deadline:
            root.update();time.sleep(.01)
        assert not app.busy,'GUI worker did not complete'
        assert not errors,errors
    try:
        session=make_session(tmp_path/'RTAUTOsession07',split=True)
        monkeypatch.setattr(filedialog,'askdirectory',lambda **_:str(session))
        app.browse();assert app.path.get()==str(session)
        app.values['start'].set('1');app.values['stop'].set('3');app.values['fmax'].set('1000')
        app.load();finish()
        assert app.section.power_dbm.shape==(2,2)
        assert app.canvas is not None and app.toolbar is not None
        assert app.timezone.get()=='EST'
        app.values['vmax'].set('-25');app.load();finish()
        assert app.figure.axes[0].collections[0].get_clim()==(-110,-25)
        mat=tmp_path/'gui.mat'
        monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **_:str(mat))
        app.export_mat();finish()
        data=io.loadmat(mat)
        assert data['power_dbm'].shape==(2,2)
        assert data['timestamp_utc'][0,0][0]=='2024-01-01T05:00:01.1234567Z'
        image=tmp_path/'gui.png'
        monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **_:str(image))
        app.save_image();assert image.read_bytes().startswith(b'\x89PNG')
        app.values['start'].set('0')
        assert not app._ready()
        assert 'Load / update plot' in str(errors[-1])
        errors.clear()
        # Full-session export ignores unapplied/invalid plot controls and also
        # works before any section has been loaded.
        app.values['max'].set('not a number'); app.section = None
        monkeypatch.setattr(filedialog,'askdirectory',lambda **_:str(tmp_path))
        app.export_session_mat();finish()
        full = tmp_path/'RTAUTOsession07_MAT'/'part_000001.mat'
        assert io.loadmat(full)['power_dbm_traces'].shape == (3,1,3)
        app.export_session_mat();finish()
        assert (tmp_path/'RTAUTOsession07_MAT_2'/'manifest.json').exists()
    finally:
        app.close()


def test_standalone_close_waits_for_mat_cleanup(tmp_path, monkeypatch):
    import threading
    from fieldfox_recording import FieldFoxRecording
    from fieldfox_recording.gui import FieldFoxApp
    tk = pytest.importorskip('tkinter')
    try:
        root = tk.Tk(); root.withdraw()
    except tk.TclError as error:
        pytest.skip(f'Tk display unavailable: {error}')
    app = FieldFoxApp(root); errors = []; started = threading.Event()
    monkeypatch.setattr(app, '_error', errors.append)
    target = tmp_path/'cancelled'
    def work():
        rec = FieldFoxRecording.open(make_session(tmp_path/'session'), cancel_event=app.cancel_event)
        def pause(*_):
            started.set()
            assert app.cancel_event.wait(10), 'Close did not cancel the owned worker'
        return rec.to_mat(target, chunk_sweeps=1, progress=pause)
    app._job(work, lambda _: None, 'Exporting')
    try:
        assert started.wait(10)
        app.close()
        deadline = time.monotonic()+10
        while app.busy and time.monotonic()<deadline:
            root.update(); time.sleep(.01)
        assert not app.busy and not errors
        app.worker.join(timeout=1)
        assert not app.worker.is_alive()
        assert not target.exists() and not list(tmp_path.glob('.fieldfox-mat-*'))
    finally:
        if app.busy:
            app.cancel_event.set(); app.worker.join(timeout=10)
        try: root.destroy()
        except tk.TclError: pass
