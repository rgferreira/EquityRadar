property controlScript : "/Users/rafaelgonzalezferreira/Documents/PersonalEquityRadar/scripts/macos/equity-radar-control.zsh"

on run
	set selectedAction to button returned of (display dialog "Start or stop the Equity Radar web application and its background maintenance services." with title "Equity Radar" buttons {"Stop everything", "Start everything"} default button "Start everything" with icon note)
	try
		if selectedAction is "Start everything" then
			set resultMessage to do shell script quoted form of controlScript & " start"
		else
			set resultMessage to do shell script quoted form of controlScript & " stop"
		end if
		display notification resultMessage with title "Equity Radar"
	on error errorMessage number errorNumber
		display dialog errorMessage with title "Equity Radar could not complete the action" buttons {"OK"} default button "OK" with icon stop
	end try
end run
