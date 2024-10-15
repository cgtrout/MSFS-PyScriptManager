# Printer Troubleshooting Guide

This document will show how to manually set up the printer in the case that the automated printer installation does not work.

I only recommend this guide as a **last resort**.  In most cases the automated printer installation of 'virtual_pos_printer' should hopefully work, but I wanted to give a fallback plan if that fails.

If the printer setup was correct it should look like this:
![image](https://github.com/user-attachments/assets/7853865d-4742-4af1-8bfe-4fc08f931e10)

If it doesn't look like this follow this guide to get the VirtualTextPrinter working on your Windows installation.

First thing to try is to open properties for port, to see if it is set up like follows in the Windows settings page "Printers & Scanners".  If changing this does not work than proceed to the next section

![image](https://github.com/user-attachments/assets/6f40caee-2b30-4077-92d6-dd7b13b98172)


# Remove any existing instances of printer and relevant ports
1. First delete 'VirtualTextPrinter' if it exists

  ![image](https://github.com/user-attachments/assets/7e449f56-9624-4ce8-afe9-d315b737bd6e)

2. Then open the "Print server properties"
  
  ![image](https://github.com/user-attachments/assets/9cbccc6f-d864-4ff8-b0af-3429c688fc5c)

3. Remove any invalid ports that may show in the "Print server properties".  Note that 127.0.0.1_9102 is correct port.  If you see any others in this area of the "Ports on this server" screen that may be conflicting - remove those.

     ![image](https://github.com/user-attachments/assets/eebc7ba7-e313-4071-a0e5-10867866b733)

4. Retry running "virtual_pos_printer" once more to see if printer installs correctly.
  - If it does not work, follow steps 1-3 once more and then procede with the next section that will show how to manually configure the printer yourself.

# How to manually set up VirtualTextPrinter

1. Click "Add device" on "Printers and scanners" settings page

  ![image](https://github.com/user-attachments/assets/f75ed886-6dcc-4557-91d2-77e2624f115a)

2. Click "Add manually"
 
  ![image](https://github.com/user-attachments/assets/76da3229-2e3a-4fbc-bc6a-0841ea498048)
3. Select "add a local printer or network printer with manual settings" then click next

  ![image](https://github.com/user-attachments/assets/a8f19118-8199-4f5b-a4c3-5a34ddd0b229)

4. If correct port is present "127.0.0.1_9102" then select it, otherwise select "Create a new port (TCP/IP)"

  ![image](https://github.com/user-attachments/assets/e47b0d68-a887-4375-a2a9-49b40db8d698)

5. If adding a new port set as follows
  
  ![image](https://github.com/user-attachments/assets/d3646c30-25f8-4fd7-8ffa-eacabdea0060)

6. Select driver "Generic / Text Only".  Click next.
 
  ![image](https://github.com/user-attachments/assets/bf7fe195-7936-4b82-bf0e-fb674bfb9c05)

7. Name printer "VirtualTextPrinter" 
  
  ![image](https://github.com/user-attachments/assets/eec46ce6-a6e2-4f06-a7c3-148d1650c48f)

8. Click next - "Do not share this printer"
9. Unfortunately there seems to be a Windows bug where port is not correctly assigned to 9102.  Open the settings page to manually configure it to be correct since the script uses port 9102

  ![image](https://github.com/user-attachments/assets/b4bab1a6-fe4f-4039-9aea-8a96dc5a729d)


If the port is configured correctly, then the "virtual_pos_printer" script should run correctly.

As a final step ensure that the printer "VirtualTextPrinter" is set as the printer in the "ACAS PRINTER" section of the Fenix EFB settings.
