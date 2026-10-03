package tw.foodsave.demo;

import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import android.content.pm.ApplicationInfo;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getKeyCode() == KeyEvent.KEYCODE_BACK && (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            Log.i("FoodSaveBack", "dispatch action=" + event.getAction() + " windowFocus=" + hasWindowFocus());
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (bridge != null && (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
                    android.webkit.WebBackForwardList history = bridge.getWebView().copyBackForwardList();
                    Log.i("FoodSaveBack", "callback index=" + history.getCurrentIndex() + " size=" + history.getSize()
                        + " canGoBack=" + bridge.getWebView().canGoBack());
                }
                if (bridge != null && bridge.getWebView().canGoBack()) {
                    bridge.getWebView().goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                    setEnabled(true);
                }
            }
        });
    }
}
