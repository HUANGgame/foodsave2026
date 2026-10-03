package tw.foodsave.demo;

import android.os.Bundle;
import android.util.Log;
import android.content.pm.ApplicationInfo;
import androidx.activity.OnBackPressedCallback;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (bridge != null && (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
                    android.webkit.WebBackForwardList history = bridge.getWebView().copyBackForwardList();
                    Log.d("FoodSaveBack", "callback index=" + history.getCurrentIndex() + " size=" + history.getSize()
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
